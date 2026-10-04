import { arArtifacts } from './ar_artifacts'
import { arAssistant } from './ar_assistant'
import { arBoot } from './ar_boot'
import { arCapabilities } from './ar_capabilities'
import { arChat } from './ar_chat'
import { arChrome } from './ar_chrome'
import { arCommandCenter } from './ar_command_center'
import { arCommon } from './ar_common'
import { arConnectors } from './ar_connectors'
import { arDiagnostics } from './ar_diagnostics'
import { arSettings } from './ar_settings'
import { defineLocale, type TranslationOverrides } from './define-locale'

export const arOverrides = {
  memoryDiscovery: {
    installed: 'مثبت',
    availableToInstall: 'متاح للتثبيت',
    installationRequired: 'التثبيت مطلوب',
    reviewInstall: 'مراجعة وتثبيت',
    exploreAll: 'استكشاف الكل…',
    missing: 'مفقود',
    installConsent: 'يثبّت الإضافة ويفعّلها مع اعتمادياتها. لا يتغير مزوّد الذاكرة النشط حتى تختاره صراحةً.',
    builtin: 'مدمج',
    providerSettings: 'إعدادات المزوّد',
    configureElsewhere: 'أعدّ المزوّد عبر CLI أو حدّث Hermes للحفظ دون تفعيل.',
    notReady: 'أكمل الإعداد وثبّت الاعتماديات. بعد التثبيت أعد تشغيل الخلفية ثم حاول مجدداً.',
    useFailed: 'تعذّر استخدام المزوّد. تحقّق من الإعدادات وأعد المحاولة.',

    active: 'نشط',
    useProvider: 'استخدام المزوّد',
    loadFailed: 'تعذّر تحميل مزوّدي الذاكرة',
    ownerChanged: 'عُد إلى الاتصال والملف الشخصي اللذين فتحت منهما برنامج التثبيت، ثم حاول مجددًا.',
    notDiscovered: 'تم تثبيت الحزمة، لكن لم يُكتشف مزوّد الذاكرة بعد. عُد إلى إعدادات الذاكرة لإعادة المحاولة.',
    installedNotice: 'تم اكتشاف المزوّد. أعدّه أولاً، ثم اختر استخدامه صراحةً.',
    backToMemory: 'العودة إلى إعدادات الذاكرة'
  },
  sharedMetrics: arCommon.sharedMetrics,
  externalOpenFailed: arChrome.externalOpenFailed,
  sessionImport: arConnectors.sessionImport,
  sendDiagnostics: arDiagnostics.sendDiagnostics,
  common: arCommon.common,
  fileMenu: arChrome.fileMenu,
  boot: arBoot.boot,
  notifications: arDiagnostics.notifications,
  remoteDisplayBanner: arBoot.remoteDisplayBanner,
  butterbar: arBoot.butterbar,
  titlebar: arChrome.titlebar,
  keybinds: arChrome.keybinds,
  language: arSettings.language,
  settings: arSettings.settings,
  skills: arCapabilities.skills,
  agents: arCapabilities.agents,
  commandCenter: arCommandCenter.commandCenter,
  messaging: arCommandCenter.messaging,
  profiles: arCommandCenter.profiles,
  modelAssignment: arSettings.modelAssignment,
  cron: arCommandCenter.cron,
  artifacts: arArtifacts.artifacts,
  artifactCard: arArtifacts.artifactCard,
  artifactPreview: arArtifacts.artifactPreview,
  sidebar: arChrome.sidebar,
  composer: arChat.composer,
  statusStack: arChat.statusStack,
  updates: arBoot.updates,
  install: arBoot.install,
  onboarding: arBoot.onboarding,
  modelPicker: arSettings.modelPicker,
  modelVisibility: arSettings.modelVisibility,
  shell: arChrome.shell,
  rightSidebar: arChrome.rightSidebar,
  preview: arArtifacts.preview,
  interfaceMode: arSettings.interfaceMode,
  zones: arChrome.zones,
  contextMenu: arChrome.contextMenu,
  assistant: arAssistant.assistant,
  prompts: arChat.prompts,
  desktop: arChat.desktop,
  errors: arDiagnostics.errors,
  tips: arChat.tips,
  ui: arCommon.ui,
  handoffTour: {
    profileTitle: 'مهمتك الأولى تعمل على الملف الشخصي الافتراضي',
    profileText:
      'يبدّل هذا الشريط بين الملفات الشخصية. المضاء الآن هو الافتراضي، حيث توجد جلسة المهمة. والآخر هو ملف الإعداد، حيث توجد محادثة الترحيب.',
    sessionsTitle: 'لكل ملف شخصي جلساته الخاصة',
    sessionsText:
      'هذه القائمة تخص الملف الافتراضي. «جلسة جديدة» تبدأ جلسة على الملف المحدد. بدّل الملف من الشريط فتتغير القائمة معه.',
    stayTitle: 'Hermes على بُعد نقرة',
    stayText: 'انتقل إلى ملف الإعداد وافتح «مرحبًا بك في Hermes» متى احتجت إلى مساعدة. ستبقى هناك.',
    localTitle: 'يمكن لهذا الجهاز تشغيل النماذج محليًا',
    localText: (model: string) =>
      `${model} يناسب أجهزتك. يعمل مجانًا، ولا تغادر المحادثات جهازك. اختره من هنا، من قائمة النماذج، متى شئت.`
  },
  freeTier: {
    offer: {
      heading: 'واصل مع Hermes',
      body: 'أنت تستخدم الحصة المجانية. إذا واصلت استخدام Hermes فستبدأ بمواجهة حدود الاستخدام. سجّل الدخول بحساب Nous مجاني للحصول على حصة أكبر.',
      signIn: 'تسجيل الدخول',
      notNow: 'ليس الآن'
    }
  }
} satisfies TranslationOverrides

export const ar = defineLocale(arOverrides)
