"""Discord interactive views; classes are built only after discord.py is available."""
from __future__ import annotations

import asyncio
import logging
from contextlib import suppress
from typing import Optional

from agent.i18n import t

logger = logging.getLogger("plugins.platforms.discord.adapter")


def define_view_classes(discord) -> dict[str, type]:
    """Register Discord UI view classes as module globals.
    Called at module load and after a lazy install so the classes exist whenever DISCORD_AVAILABLE."""
    from plugins.platforms.discord.adapter import (
        _read_discord_prompt_timeout, _unauthorized, _t_discord,
        _truncate_discord_component_text, _prefix_within_utf16_limit,
        _DISCORD_BUTTON_LABEL_LIMIT, _DISCORD_SELECT_FIELD_LIMIT,
        _DISCORD_SELECT_PLACEHOLDER_LIMIT, _DISCORD_SELECT_MAX_OPTIONS,
        _DISCORD_SELECT_MAX_ROWS, _DISCORD_MODEL_SELECT_CAPACITY,
        _DISCORD_ELLIPSIS, _DISCORD_EMBED_TITLE_LIMIT, utf16_len,
    )

    class _HermesView(discord.ui.View):
        """Shared plumbing for Hermes component views: allowlist auth, single-use
        ``resolved`` flag, ``_message`` handle for timeout edits."""

        def __init__(self, allowed_user_ids: set, allowed_role_ids: Optional[set], *, timeout):
            super().__init__(timeout=timeout)
            self.allowed_user_ids = allowed_user_ids
            self.allowed_role_ids = allowed_role_ids or set()
            # The adapter's live allowlist check, bound in ``_send_prompt``.
            self.live_auth = None
            self.resolved = False
            self._message = None

        def _check_auth(self, interaction: discord.Interaction) -> bool:
            from plugins.platforms.discord.adapter_component_auth import _component_check_auth
            return _component_check_auth(
                interaction, self.allowed_user_ids, self.allowed_role_ids, live_auth=self.live_auth)

        async def _gate(self, interaction: discord.Interaction, *, resolved_msg: Optional[str], unauth_msg: str) -> bool:
            """Reject (ephemerally) an already-resolved or unauthorized click; True when it may proceed."""
            if resolved_msg is not None and self.resolved:
                await interaction.response.send_message(resolved_msg, ephemeral=True)
                return False
            if not self._check_auth(interaction):
                await interaction.response.send_message(unauth_msg, ephemeral=True)
                return False
            return True

        def _disable_all(self) -> None:
            for child in self.children:
                child.disabled = True

        @staticmethod
        def _first_embed(message):
            return message.embeds[0] if message.embeds else None

        async def _expire_embed(self, footer: str) -> None:
            """Grey out the original message's embed after a timeout (best effort)."""
            msg = self._message
            if msg:
                try:
                    embed = self._first_embed(msg)
                    if embed:
                        embed.color = discord.Color.greyple()
                        embed.set_footer(text=footer)
                    await msg.edit(embed=embed, view=self)
                except Exception:
                    pass  # message deleted or too old to edit

        async def _finalize_embed(self, interaction: discord.Interaction, color, footer: str) -> None:
            """Mark resolved, stamp the embed (color + footer), disable buttons, edit in place."""
            self.resolved = True
            embed = self._first_embed(interaction.message)
            if embed:
                embed.color = color
                embed.set_footer(text=footer)
            self._disable_all()
            await interaction.response.edit_message(embed=embed, view=self)

        def _localize_buttons(self, **keys_by_attr: str) -> None:
            """Relabel decorator-declared buttons from the catalog (decorators run at import, before
            the language is known). Button labels cap at 80 UTF-16 units."""
            for attr, key in keys_by_attr.items():
                item = getattr(self, attr, None)
                if not hasattr(item, "label"):
                    # Not materialised as an item on the instance (stubbed discord in tests / other
                    # discord.py builds): locate the child whose callback is the decorated method.
                    item = next(
                        (child for child in (getattr(self, "children", None) or [])
                         if getattr(getattr(child, "callback", None), "__name__", None) == attr
                         or getattr(getattr(getattr(child, "callback", None), "callback", None), "__name__", None) == attr),
                        None)
                if hasattr(item, "label"):
                    item.label = _t_discord(key, _DISCORD_BUTTON_LABEL_LIMIT)

        async def on_timeout(self):
            self.resolved = True
            self._disable_all()
            await self._expire_embed(t("platform.discord.prompt.expired_footer"))

    class CronActionsView(_HermesView):
        """Typed controls for a cron delivery; deterministic actions never enter the agent loop."""

        def __init__(
            self, adapter, job_id: str, expected_user_id: str, actions: list[str],
            allowed_user_ids: set, allowed_role_ids: Optional[set] = None,
            approval_id: str = "",
        ):
            super().__init__(allowed_user_ids, allowed_role_ids, timeout=7 * 24 * 60 * 60)
            self.adapter = adapter
            self.job_id = str(job_id)
            self.approval_id = str(approval_id or "")
            self.expected_user_id = str(expected_user_id)
            self.actions = tuple(dict.fromkeys(str(a) for a in actions))
            self._action_lock = asyncio.Lock()
            self._calendar_resolved = False
            # This view is fully dynamic: clear any decorator-materialized children inherited from
            # discord.py and add exactly the actions declared by the scheduler contract.
            for child in list(getattr(self, "children", None) or []):
                self.remove_item(child)
            button_cls = discord.ui.Button
            if "rerun" in self.actions:
                button = button_cls(
                    label="Relancer", style=discord.ButtonStyle.blurple,
                    custom_id="hermes:cron:rerun")
                button.callback = self._resolve_rerun
                self.add_item(button)
            if self.approval_id and "calendar_authorize" in self.actions:
                button = button_cls(
                    label="Autoriser", style=discord.ButtonStyle.green,
                    custom_id="hermes:cron-calendar:authorize")
                button.callback = self._authorize_calendar
                self.add_item(button)
            if self.approval_id and "calendar_refuse" in self.actions:
                button = button_cls(
                    label="Refuser", style=discord.ButtonStyle.red,
                    custom_id="hermes:cron-calendar:refuse")
                button.callback = self._refuse_calendar
                self.add_item(button)

        def _check_auth(self, interaction: discord.Interaction) -> bool:
            user_id = str(getattr(getattr(interaction, "user", None), "id", "") or "")
            return user_id == self.expected_user_id and super()._check_auth(interaction)

        async def _resolve_rerun(self, interaction: discord.Interaction) -> None:
            if not self._check_auth(interaction):
                await interaction.response.send_message(_unauthorized(), ephemeral=True)
                return
            async with self._action_lock:
                await interaction.response.defer(ephemeral=True)
                try:
                    message = await self.adapter._dispatch_cron_action(
                        interaction, self.job_id, "rerun")
                except Exception as exc:
                    logger.exception("Failed to rerun cron job %s from Discord", self.job_id)
                    message = f"La relance a échoué : {exc}"
                await interaction.followup.send(message, ephemeral=True)

        async def _resolve_calendar(self, interaction: discord.Interaction, decision: str) -> None:
            async with self._action_lock:
                if self._calendar_resolved:
                    await interaction.response.send_message(
                        "Cette demande a déjà été traitée.", ephemeral=True)
                    return
                if not self._check_auth(interaction):
                    await interaction.response.send_message(_unauthorized(), ephemeral=True)
                    return
                self._calendar_resolved = True
                await interaction.response.defer(ephemeral=True)
                try:
                    message = await self.adapter._dispatch_cron_calendar_authorization(
                        interaction, self.approval_id, decision)
                except Exception:
                    self._calendar_resolved = False
                    logger.exception(
                        "Failed to dispatch Discord cron calendar decision %s", self.approval_id)
                    await interaction.followup.send(
                        "La décision n'a pas pu être transmise. Réessaie.", ephemeral=True)
                    return
                for child in getattr(self, "children", None) or []:
                    if str(getattr(child, "custom_id", "")).startswith("hermes:cron-calendar:"):
                        child.disabled = True
                with suppress(Exception):
                    await interaction.message.edit(view=self)
                await interaction.followup.send(message, ephemeral=True)

        async def _authorize_calendar(self, interaction: discord.Interaction) -> None:
            await self._resolve_calendar(interaction, "authorize")

        async def _refuse_calendar(self, interaction: discord.Interaction) -> None:
            await self._resolve_calendar(interaction, "refuse")

    class CronCalendarApprovalView(_HermesView):
        """Non-blocking Authorize/Refuse controls for a continuable Discord cron brief."""

        def __init__(
            self, adapter, approval_id: str, expected_user_id: str,
            allowed_user_ids: set, allowed_role_ids: Optional[set] = None,
        ):
            super().__init__(allowed_user_ids, allowed_role_ids, timeout=7 * 24 * 60 * 60)
            self.adapter = adapter
            self.approval_id = approval_id
            self.expected_user_id = str(expected_user_id)
            self._decision_lock = asyncio.Lock()
            btn_cls = getattr(getattr(discord, "ui", None), "Button", None)
            style_cls = getattr(discord, "ButtonStyle", None)
            if btn_cls is not None and style_cls is not None and not getattr(self, "children", None):
                authorize_btn = btn_cls(
                    label="Autoriser",
                    style=getattr(style_cls, "green", getattr(style_cls, "success", 1)),
                    custom_id="hermes:cron-calendar:authorize",
                )
                authorize_btn.callback = self.authorize
                self.add_item(authorize_btn)
                refuse_btn = btn_cls(
                    label="Refuser",
                    style=getattr(style_cls, "red", getattr(style_cls, "danger", 3)),
                    custom_id="hermes:cron-calendar:refuse",
                )
                refuse_btn.callback = self.refuse
                self.add_item(refuse_btn)

        def _check_auth(self, interaction: discord.Interaction) -> bool:
            user_id = str(getattr(getattr(interaction, "user", None), "id", "") or "")
            return user_id == self.expected_user_id and super()._check_auth(interaction)

        async def _resolve(self, interaction: discord.Interaction, decision: str) -> None:
            async with self._decision_lock:
                if not await self._gate(
                    interaction,
                    resolved_msg="Cette demande a déjà été traitée.",
                    unauth_msg=_unauthorized(),
                ):
                    return
                self.resolved = True
                await interaction.response.defer(ephemeral=True)
                try:
                    await self.adapter._dispatch_cron_calendar_authorization(
                        interaction, self.approval_id, decision)
                except Exception:
                    self.resolved = False
                    logger.exception(
                        "Failed to dispatch Discord cron calendar decision %s", self.approval_id)
                    with suppress(Exception):
                        await interaction.followup.send(
                            "La décision n'a pas pu être transmise. Réessaie.", ephemeral=True)
                    return
                self._disable_all()
                with suppress(Exception):
                    await interaction.message.edit(view=self)
                with suppress(Exception):
                    await interaction.followup.send("Décision transmise.", ephemeral=True)

        @discord.ui.button(
            label="Autoriser", style=discord.ButtonStyle.green,
            custom_id="hermes:cron-calendar:authorize",
        )
        async def authorize(self, interaction: discord.Interaction, button: discord.ui.Button):
            await self._resolve(interaction, "authorize")

        @discord.ui.button(
            label="Refuser", style=discord.ButtonStyle.red,
            custom_id="hermes:cron-calendar:refuse",
        )
        async def refuse(self, interaction: discord.Interaction, button: discord.ui.Button):
            await self._resolve(interaction, "refuse")

    class ExecApprovalView(_HermesView):
        """Allow Once / Allow Session / Always Allow / Deny buttons for a dangerous command.
        Clicks call ``resolve_gateway_approval()`` — the same mechanism as the text ``/approve`` flow."""

        def __init__(
            self, session_key: str, allowed_user_ids: set, allowed_role_ids: Optional[set] = None,
            require_admin: bool = False, admin_user_ids: Optional[set] = None,
            allow_permanent: bool = True, allow_session: bool = True, smart_denied: bool = False,
        ):
            super().__init__(allowed_user_ids, allowed_role_ids, timeout=_read_discord_prompt_timeout())
            self.session_key = session_key
            self.require_admin = require_admin
            self.admin_user_ids = {str(a).strip() for a in (admin_user_ids or set()) if str(a).strip()}
            self._localize_buttons(
                allow_once="gateway.exec_approval.action_once", allow_session="gateway.exec_approval.action_session",
                allow_always="gateway.exec_approval.action_always", deny="gateway.exec_approval.action_deny")
            if smart_denied or not allow_session:
                self.remove_item(self.allow_session)
                self.remove_item(self.allow_always)
            elif not allow_permanent:
                self.remove_item(self.allow_always)

        def _check_auth(self, interaction: discord.Interaction) -> bool:
            """Base admission always required; with ``require_admin`` the clicker must
            also be an admin. Fails closed (logged once) when no admins are configured."""
            if not super()._check_auth(interaction):
                return False
            if not self.require_admin:
                return True
            user = getattr(interaction, "user", None)
            try:
                uid = str(getattr(user, "id", "") or "")
            except Exception:
                uid = ""
            if uid and uid in self.admin_user_ids:
                return True
            if not self.admin_user_ids:
                logger.warning(
                    "[Discord] require_admin_for_exec_approval is enabled but "
                    "no admins are configured (allow_admin_from is empty) — "
                    "exec approval buttons are disabled for everyone. Add "
                    "admin user IDs under the discord platform's "
                    "allow_admin_from, or disable the toggle."
                )
            return False

        async def _resolve(self, interaction: discord.Interaction, choice: str, color: discord.Color, label_key: str):
            """Resolve the approval via the gateway approval queue and update the embed."""
            if not await self._gate(
                interaction, resolved_msg=t("platform.discord.approval.already_resolved"),
                unauth_msg=_unauthorized(),
            ):
                return
            label = t(label_key)
            self.resolved = True
            # Unblock the waiting agent thread FIRST. A click after the approval
            # wait timed out (count == 0) must not claim "Approved".
            try:
                from tools.approval import resolve_gateway_approval
                count = resolve_gateway_approval(self.session_key, choice)
                logger.info(
                    "Discord button resolved %d approval(s) for session %s (choice=%s, user=%s)",
                    count, self.session_key, choice, interaction.user.display_name,
                )
            except Exception as exc:
                logger.error("Failed to resolve gateway approval from button: %s", exc)
                count = 0
            if not count:
                color = discord.Color.dark_grey()
                label = t("platform.discord.approval.expired")
            await self._finalize_embed(
                interaction, color,
                t("platform.discord.approval.by_user", label=label, user=interaction.user.display_name) if count else label)

        # Decorator labels are placeholders; ``_localize_buttons`` in __init__ sets the real text.
        @discord.ui.button(label="Allow Once", style=discord.ButtonStyle.green)
        async def allow_once(self, interaction: discord.Interaction, button: discord.ui.Button):
            await self._resolve(interaction, "once", discord.Color.green(), "platform.discord.approval.resolved_once")

        @discord.ui.button(label="Allow Session", style=discord.ButtonStyle.grey)
        async def allow_session(self, interaction: discord.Interaction, button: discord.ui.Button):
            await self._resolve(interaction, "session", discord.Color.blue(), "platform.discord.approval.resolved_session")

        @discord.ui.button(label="Always Allow", style=discord.ButtonStyle.blurple)
        async def allow_always(self, interaction: discord.Interaction, button: discord.ui.Button):
            await self._resolve(interaction, "always", discord.Color.purple(), "platform.discord.approval.resolved_always")

        @discord.ui.button(label="Deny", style=discord.ButtonStyle.red)
        async def deny(self, interaction: discord.Interaction, button: discord.ui.Button):
            await self._resolve(interaction, "deny", discord.Color.red(), "platform.discord.approval.resolved_deny")

    class SlashConfirmView(_HermesView):
        """Approve Once / Always Approve / Cancel for slash-command confirmations (``/reload-mcp``,
        ``GatewayRunner._request_slash_confirm``); clicks call ``tools.slash_confirm.resolve(...)``."""

        def __init__(self, session_key: str, confirm_id: str, allowed_user_ids: set, allowed_role_ids: Optional[set] = None):
            super().__init__(allowed_user_ids, allowed_role_ids, timeout=_read_discord_prompt_timeout())
            self.session_key = session_key
            self.confirm_id = confirm_id
            self._localize_buttons(
                approve_once="platform.discord.slash_confirm.approve_once",
                approve_always="platform.discord.slash_confirm.always_approve",
                cancel="platform.discord.slash_confirm.cancel")

        async def _resolve(self, interaction: discord.Interaction, choice: str, color: discord.Color, label_key: str):
            if not await self._gate(
                interaction, resolved_msg=t("platform.discord.slash_confirm.already_resolved"),
                unauth_msg=_unauthorized(),
            ):
                return
            await self._finalize_embed(
                interaction, color,
                t("platform.discord.approval.by_user", label=t(label_key), user=interaction.user.display_name))
            # A returned follow-up message is posted in the same channel.
            try:
                from tools import slash_confirm as _slash_confirm_mod
                result_text = await _slash_confirm_mod.resolve(self.session_key, self.confirm_id, choice)
                if result_text:
                    await interaction.followup.send(result_text)
                logger.info(
                    "Discord button resolved slash-confirm for session %s "
                    "(choice=%s, user=%s)",
                    self.session_key, choice, interaction.user.display_name,
                )
            except Exception as exc:
                logger.error("Discord slash-confirm resolve failed: %s", exc, exc_info=True)

        @discord.ui.button(label="Approve Once", style=discord.ButtonStyle.green)
        async def approve_once(self, interaction: discord.Interaction, button: discord.ui.Button):
            await self._resolve(interaction, "once", discord.Color.green(), "platform.discord.slash_confirm.resolved_once")

        @discord.ui.button(label="Always Approve", style=discord.ButtonStyle.blurple)
        async def approve_always(self, interaction: discord.Interaction, button: discord.ui.Button):
            await self._resolve(interaction, "always", discord.Color.purple(), "platform.discord.slash_confirm.resolved_always")

        @discord.ui.button(label="Cancel", style=discord.ButtonStyle.red)
        async def cancel(self, interaction: discord.Interaction, button: discord.ui.Button):
            await self._resolve(interaction, "cancel", discord.Color.greyple(), "platform.discord.slash_confirm.resolved_cancel")

    class UpdatePromptView(_HermesView):
        """Yes/No buttons for ``hermes update`` prompts; the answer is written to
        ``.update_response`` for the detached update process to pick up."""

        def __init__(self, session_key: str, allowed_user_ids: set, allowed_role_ids: Optional[set] = None):
            super().__init__(allowed_user_ids, allowed_role_ids, timeout=_read_discord_prompt_timeout())
            self.session_key = session_key
            self._localize_buttons(yes_btn="platform.discord.prompt.affirm", no_btn="platform.discord.prompt.negate")

        async def _respond(self, interaction: discord.Interaction, answer: str, color: discord.Color, label_key: str):
            if not await self._gate(interaction, resolved_msg=t("platform.discord.prompt.already_answered"), unauth_msg=_unauthorized()):
                return
            await self._finalize_embed(
                interaction, color,
                t("platform.discord.approval.by_user", label=t(label_key), user=interaction.user.display_name))
            try:
                from hermes_constants import get_hermes_home
                response_path = get_hermes_home() / ".update_response"
                tmp = response_path.with_suffix(".tmp")
                tmp.write_text(answer, encoding="utf-8")
                tmp.replace(response_path)
                logger.info("Discord update prompt answered '%s' by %s", answer, interaction.user.display_name)
            except Exception as exc:
                logger.error("Failed to write update response: %s", exc)

        @discord.ui.button(label="Yes", style=discord.ButtonStyle.green, emoji="✓")
        async def yes_btn(self, interaction: discord.Interaction, button: discord.ui.Button):
            await self._respond(interaction, "y", discord.Color.green(), "platform.discord.prompt.affirm")

        @discord.ui.button(label="No", style=discord.ButtonStyle.red, emoji="✗")
        async def no_btn(self, interaction: discord.Interaction, button: discord.ui.Button):
            await self._respond(interaction, "n", discord.Color.red(), "platform.discord.prompt.negate")

    class ModelPickerView(_HermesView):
        """Two-step select-menu model picker: provider dropdown → model dropdown,
        editing the original message in place. Times out after 2 minutes."""

        def __init__(
            self, providers: list, current_model: str, current_provider: str, session_key: str,
            on_model_selected, allowed_user_ids: set, allowed_role_ids: Optional[set] = None,
        ):
            super().__init__(allowed_user_ids, allowed_role_ids, timeout=120)
            self.providers = providers
            self.current_model = current_model
            self.current_provider = current_provider
            self.session_key = session_key
            self.on_model_selected = on_model_selected
            self._selected_provider: str = ""
            self._pending_expensive_model: str = ""
            self._build_provider_select()

        def _add_button(self, label: str, style, custom_id: str, callback) -> None:
            btn = discord.ui.Button(label=label, style=style, custom_id=custom_id)
            btn.callback = callback
            self.add_item(btn)

        def _add_select(self, placeholder: str, options: list, custom_id: str, callback) -> None:
            select = discord.ui.Select(placeholder=placeholder, options=options, custom_id=custom_id)
            select.callback = callback
            self.add_item(select)

        async def _edit(self, interaction: discord.Interaction, description: str, *, view=..., **embed_kw) -> None:
            """Edit the picker message in place with a config embed (``view`` defaults to self)."""
            await interaction.response.edit_message(
                embed=self._config_embed(description, **embed_kw), view=self if view is ... else view,
            )

        def _build_provider_select(self):
            """Build the provider dropdown menu."""
            self.clear_items()
            options = []
            for p in self.providers:
                count = p.get("total_models", len(p.get("models", [])))
                options.append(discord.SelectOption(
                    label=_t_discord("platform.discord.picker.provider_option", _DISCORD_SELECT_FIELD_LIMIT, provider=p["name"], count=str(count)),
                    value=p["slug"],
                    description=_t_discord("platform.discord.picker.current", _DISCORD_SELECT_FIELD_LIMIT) if p.get("is_current") else None,
                ))
            if not options:
                return
            self._add_select(
                _t_discord("platform.discord.picker.provider_placeholder", _DISCORD_SELECT_PLACEHOLDER_LIMIT),
                options[:_DISCORD_SELECT_MAX_OPTIONS], "model_provider_select", self._on_provider_selected,
            )
            self._add_button(_t_discord("platform.discord.picker.cancel", _DISCORD_BUTTON_LABEL_LIMIT), discord.ButtonStyle.red, "model_cancel", self._on_cancel)

        def _build_model_select(self, provider_slug: str):
            """Model dropdown(s) for one provider.
            Select caps at 25 options and View at 5 rows (2 reserved for Back/Cancel), so models are
            partitioned across up to 3 selects (75) rather than truncated (tail entries would vanish)."""
            self.clear_items()
            provider = next((p for p in self.providers if p["slug"] == provider_slug), None)
            if not provider:
                return
            models = provider.get("models", [])
            if not models:
                return
            chunks = [
                models[i : i + _DISCORD_SELECT_MAX_OPTIONS]
                for i in range(0, len(models), _DISCORD_SELECT_MAX_OPTIONS)
            ][: _DISCORD_SELECT_MAX_ROWS - 2]
            placeholder_base = t("platform.discord.picker.model_placeholder", provider=provider.get("name", provider_slug))
            for idx, chunk in enumerate(chunks):
                options = [
                    discord.SelectOption(
                        label=_truncate_discord_component_text(model_id.split("/")[-1], _DISCORD_SELECT_FIELD_LIMIT),
                        value=_truncate_discord_component_text(model_id, _DISCORD_SELECT_FIELD_LIMIT),
                    )
                    for model_id in chunk
                ]
                suffix = f" ({idx + 1}/{len(chunks)})" if len(chunks) > 1 else ""
                self._add_select(
                    _truncate_discord_component_text(f"{placeholder_base}{suffix}...", _DISCORD_SELECT_PLACEHOLDER_LIMIT),
                    options, f"model_model_select_{idx}", self._on_model_selected)
            self._add_button(_t_discord("platform.discord.picker.back", _DISCORD_BUTTON_LABEL_LIMIT), discord.ButtonStyle.grey, "model_back", self._on_back)
            self._add_button(_t_discord("platform.discord.picker.cancel", _DISCORD_BUTTON_LABEL_LIMIT), discord.ButtonStyle.red, "model_cancel2", self._on_cancel)

        def _build_expensive_confirm(self, model_id: str):
            """Build confirmation buttons for unusually expensive models."""
            self.clear_items()
            self._pending_expensive_model = model_id
            self._add_button(_t_discord("platform.discord.picker.switch_anyway", _DISCORD_BUTTON_LABEL_LIMIT), discord.ButtonStyle.red, "model_expensive_confirm", self._on_expensive_confirm)
            self._add_button(_t_discord("platform.discord.picker.cancel", _DISCORD_BUTTON_LABEL_LIMIT), discord.ButtonStyle.grey, "model_expensive_cancel", self._on_cancel)

        async def _expensive_warning_for(self, model_id: str):
            try:
                from hermes_cli.model_selection_guards import combined_selection_warning
                # Pricing lookup can hit models.dev on a cache miss — keep it off the event loop.
                return await asyncio.to_thread(combined_selection_warning, model_id, provider=self._selected_provider)
            except Exception:
                return None

        def _config_embed(self, description: str, *, title: Optional[str] = None, color=None):
            title = title if title is not None else t("platform.discord.picker.title")
            return discord.Embed(
                title=_truncate_discord_component_text(title, _DISCORD_EMBED_TITLE_LIMIT), description=description,
                color=discord.Color.blue() if color is None else color)

        async def _on_provider_selected(self, interaction: discord.Interaction):
            if not await self._gate(interaction, resolved_msg=None, unauth_msg=_unauthorized()):
                return
            provider_slug = interaction.data["values"][0]
            self._selected_provider = provider_slug
            provider = next((p for p in self.providers if p["slug"] == provider_slug), None)
            pname = provider.get("name", provider_slug) if provider else provider_slug
            self._build_model_select(provider_slug)
            # `shown` counts models actually rendered across the partitioned selects (≤ 75).
            total = provider.get("total_models", 0) if provider else 0
            shown = min(len(provider.get("models", [])), _DISCORD_MODEL_SELECT_CAPACITY) if provider else 0
            extra = f"\n*{t('platform.discord.picker.more_available', count=str(total - shown))}*" if total > shown else ""
            await self._edit(interaction, t("platform.discord.picker.select_model", provider=pname, extra=extra))

        async def _switch_selected_model(self, interaction: discord.Interaction, model_id: str):
            if not await self._gate(interaction, resolved_msg=t("platform.discord.picker.already_resolved"), unauth_msg=_unauthorized()):
                return
            self.resolved = True
            self.clear_items()
            await self._edit(
                interaction, t("platform.discord.picker.switching", model=model_id),
                title=t("platform.discord.picker.switching_title"), view=None)
            try:
                result_text = await self.on_model_selected(str(interaction.channel_id), model_id, self._selected_provider)
            except Exception as exc:
                result_text = t("platform.discord.picker.switch_error", error=str(exc))
            await interaction.edit_original_response(
                embed=self._config_embed(result_text, title=t("platform.discord.picker.switched_title"), color=discord.Color.green()),
                view=None,
            )

        async def _on_model_selected(self, interaction: discord.Interaction):
            if not await self._gate(interaction, resolved_msg=t("platform.discord.picker.already_resolved"), unauth_msg=_unauthorized()):
                return
            model_id = interaction.data["values"][0]
            warning = await self._expensive_warning_for(model_id)
            if warning is not None:
                self._build_expensive_confirm(model_id)
                await self._edit(interaction, warning.message, title=f"⚠ {warning.title}", color=discord.Color.red())
                return
            await self._switch_selected_model(interaction, model_id)

        async def _on_expensive_confirm(self, interaction: discord.Interaction):
            if not await self._gate(interaction, resolved_msg=None, unauth_msg=_unauthorized()):
                return
            if not self._pending_expensive_model:
                await interaction.response.send_message(t("platform.discord.picker.expired_toast"), ephemeral=True)
                return
            await self._switch_selected_model(interaction, self._pending_expensive_model)

        async def _on_back(self, interaction: discord.Interaction):
            if not await self._gate(interaction, resolved_msg=None, unauth_msg=_unauthorized()):
                return
            self._build_provider_select()
            try:
                from hermes_cli.providers import get_label
                provider_label = get_label(self.current_provider)
            except Exception:
                provider_label = self.current_provider
            await self._edit(
                interaction,
                t("platform.discord.picker.select_provider",
                  model=self.current_model or t("platform.discord.picker.unknown_model"), provider=provider_label),
            )

        async def _on_cancel(self, interaction: discord.Interaction):
            if not await self._gate(interaction, resolved_msg=None, unauth_msg=_unauthorized()):
                return
            self.resolved = True
            self.clear_items()
            await self._edit(interaction, t("platform.discord.picker.cancelled"), color=discord.Color.greyple())

        async def on_timeout(self):
            self.resolved = True
            self.clear_items()
            msg = self._message
            if msg:
                try:
                    embed = self._config_embed(t("platform.discord.picker.expired"), color=discord.Color.greyple())
                    await msg.edit(embed=embed, view=self)
                except Exception:
                    pass

    class ChoicePickerView(_HermesView):
        """Flat single-select picker for finite-choice commands (/reasoning, /fast); 2-minute timeout."""

        def __init__(self, choices: list, on_choice_selected, allowed_user_ids: set, allowed_role_ids: Optional[set] = None):
            super().__init__(allowed_user_ids, allowed_role_ids, timeout=120)
            self.choices = list(choices)[:_DISCORD_SELECT_MAX_OPTIONS]
            self.on_choice_selected = on_choice_selected
            options = []
            for choice in self.choices:
                label = str(choice.get("label") or choice.get("value") or "")
                options.append(
                    discord.SelectOption(
                        label=_truncate_discord_component_text(label, _DISCORD_SELECT_FIELD_LIMIT),
                        value=str(choice.get("value") or ""),
                        description=_t_discord("platform.discord.picker.current", _DISCORD_SELECT_FIELD_LIMIT) if choice.get("is_current") else None,
                    )
                )
            select = discord.ui.Select(
                placeholder=_t_discord("platform.discord.picker.choice_placeholder", _DISCORD_SELECT_PLACEHOLDER_LIMIT), options=options)
            select.callback = self._on_select
            self.add_item(select)

        async def _on_select(self, interaction: discord.Interaction):
            if not self._check_auth(interaction):
                await interaction.response.send_message(_unauthorized(), ephemeral=True)
                return
            if self.resolved:
                await interaction.response.defer()
                return
            self.resolved = True
            value = interaction.data.get("values", [""])[0]
            try:
                result_text = await self.on_choice_selected(str(interaction.channel_id), value)
            except Exception as exc:
                logger.error("Choice picker selection failed: %s", exc)
                result_text = t("platform.discord.picker.choice_error", error=str(exc))
            embed = discord.Embed(description=result_text, color=discord.Color.green())
            self.clear_items()
            self.stop()
            await interaction.response.edit_message(embed=embed, view=self)

        async def on_timeout(self):
            if self.resolved:
                return
            msg = self._message
            if msg is not None:
                try:
                    embed = discord.Embed(description=t("platform.discord.picker.choice_expired"), color=discord.Color.greyple())
                    self.clear_items()
                    await msg.edit(embed=embed, view=self)
                except Exception:
                    pass

    class ClarifyChoiceView(_HermesView):
        """One button per clarify choice (max 24) plus ``✏️ Other``. A numeric click resolves the
        gateway clarify entry immediately; ``Other`` flips to text-capture (next message answers).
        Single-use: after the first valid click all buttons disable."""

        def __init__(self, choices: list[str], clarify_id: str, allowed_user_ids: set, allowed_role_ids: Optional[set] = None):
            super().__init__(allowed_user_ids, allowed_role_ids, timeout=_read_discord_prompt_timeout())
            self.choices = list(choices)[:24]
            self.clarify_id = clarify_id
            for index, choice in enumerate(self.choices):
                button = discord.ui.Button(
                    label=self._button_label(index, choice), style=discord.ButtonStyle.primary,
                    custom_id=f"clarify:{clarify_id}:{index}",
                )
                button.callback = self._make_choice_callback(index, choice)
                self.add_item(button)
            other_btn = discord.ui.Button(
                label=_t_discord("platform.discord.prompt.other", _DISCORD_BUTTON_LABEL_LIMIT), style=discord.ButtonStyle.secondary,
                custom_id=f"clarify:{clarify_id}:other",
            )
            other_btn.callback = self._on_other
            self.add_item(other_btn)

        @staticmethod
        def _button_label(index: int, choice: str) -> str:
            """``"N. <choice>"`` within Discord's 80-char (UTF-16) label cap.
            Mobile wraps early, so long choices cut at a word boundary in the trailing half, else a
            soft boundary (``- , . )``, inclusive), else hard."""
            prefix = f"{index + 1}. "
            budget = _DISCORD_BUTTON_LABEL_LIMIT - utf16_len(prefix)
            if utf16_len(choice) <= budget:
                return f"{prefix}{choice}"
            truncated = _prefix_within_utf16_limit(choice, max(0, budget - utf16_len(_DISCORD_ELLIPSIS))).rstrip()
            cut_at = -1
            space = truncated.rfind(" ")
            if space >= len(truncated) // 2:
                cut_at = space
            if cut_at < 0:
                latest_soft = max((truncated.rfind(s) for s in ("-", ",", ".", ")")), default=-1)
                if latest_soft >= len(truncated) // 2:
                    cut_at = latest_soft + 1
            if cut_at > 0:
                truncated = truncated[:cut_at]
            return f"{prefix}{truncated.rstrip() + _DISCORD_ELLIPSIS}"

        def _make_choice_callback(self, index: int, choice: str):
            async def _callback(interaction: "discord.Interaction"):
                await self._resolve_choice(interaction, index, choice)
            return _callback

        async def _finish(self, interaction: "discord.Interaction", color, footer: str, *, log_edit_failure: bool) -> None:
            """Disable the buttons and stamp the embed; fall back to a bare defer."""
            self.resolved = True
            self._disable_all()
            embed = self._first_embed(interaction.message) if interaction.message else None
            if embed:
                embed.color = color
                embed.set_footer(text=footer)
            try:
                await interaction.response.edit_message(embed=embed, view=self)
            except Exception:
                if log_edit_failure:
                    logger.debug("Discord clarify edit_message failed for %s", self.clarify_id, exc_info=True)
                try:
                    await interaction.response.defer()
                except Exception:
                    pass

        async def _resolve_choice(self, interaction: "discord.Interaction", index: int, choice: str) -> None:
            """Resolve the clarify with a chosen option."""
            if not await self._gate(
                interaction, resolved_msg=t("platform.discord.prompt.clarify_already_answered"),
                unauth_msg=_unauthorized(),
            ):
                return
            display_name = getattr(getattr(interaction, "user", None), "display_name", "user")
            await self._finish(
                interaction, discord.Color.green(),
                t("platform.discord.prompt.answered_by", user=display_name, choice=choice), log_edit_failure=True)
            # Round-trip the canonical choice text from the entry, not the button label.
            resolved_text: Optional[str] = None
            try:
                from tools.clarify_gateway import _entries as _clarify_entries  # type: ignore
                entry = _clarify_entries.get(self.clarify_id)
                if entry and entry.choices and 0 <= index < len(entry.choices):
                    resolved_text = entry.choices[index]
            except Exception:
                resolved_text = None
            if resolved_text is None:
                resolved_text = choice
            try:
                from tools.clarify_gateway import resolve_gateway_clarify
                resolved = resolve_gateway_clarify(self.clarify_id, resolved_text)
                logger.info(
                    "Discord clarify button resolved (id=%s, choice=%r, user=%s, ok=%s)",
                    self.clarify_id, resolved_text,
                    getattr(getattr(interaction, "user", None), "display_name", "?"), resolved,
                )
            except Exception as exc:
                logger.error("Discord clarify resolve_gateway_clarify failed (id=%s): %s", self.clarify_id, exc)

        async def _on_other(self, interaction: "discord.Interaction") -> None:
            """Flip the clarify entry into text-capture mode."""
            if not await self._gate(
                interaction, resolved_msg=t("platform.discord.prompt.clarify_already_answered"),
                unauth_msg=_unauthorized(),
            ):
                return
            # Don't pop: the gateway text-intercept needs the entry until the user types.
            try:
                from tools.clarify_gateway import mark_awaiting_text
                mark_awaiting_text(self.clarify_id)
            except Exception as exc:
                logger.warning("Discord clarify mark_awaiting_text failed (id=%s): %s", self.clarify_id, exc)
            display_name = getattr(getattr(interaction, "user", None), "display_name", "user")
            await self._finish(
                interaction, discord.Color.blue(),
                t("platform.discord.prompt.awaiting_typed", user=display_name), log_edit_failure=False)

    return {cls.__name__: cls for cls in (
        CronActionsView, CronCalendarApprovalView, ExecApprovalView,
        SlashConfirmView, UpdatePromptView, ModelPickerView,
        ChoicePickerView, ClarifyChoiceView,
    )}
