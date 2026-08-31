/**
 * Welsh (cy-GB) message catalogue - DRAFT.
 *
 * **These translations were drafted for a demonstration. They have not been produced or
 * checked by a professional translator, and no clinician has reviewed the wording of
 * anything that carries advice.** They must not be relied on.
 *
 * Welsh is included because Welsh language provision is a statutory duty for public bodies
 * in Wales, so it is the locale most likely to be a real requirement rather than a
 * nice-to-have. The point of shipping it is to prove the mechanism carries a second
 * language end to end - not to claim the service speaks Welsh.
 *
 * Two safeguards follow from that, both enforced in code rather than by convention:
 *
 * 1. The locale is marked DRAFT in LOCALE_META, which shows a notice on every page.
 * 2. Keys in SAFETY_CRITICAL_KEYS render with the English alongside the Welsh, so nobody
 *    acts on unchecked wording.
 *
 * A missing key falls back to English rather than showing a raw key, so a partial
 * translation degrades into a usable page rather than a broken one.
 */

import type { MessageKey } from "./en-GB";

export const messages: Partial<Record<MessageKey, string>> = {
  // --- Shared ---------------------------------------------------------------
  "common.signOut": "Allgofnodi",
  "common.signedInAs": "Wedi mewngofnodi fel {name}",
  "common.back": "Yn ôl",
  "common.cancel": "Canslo",
  "common.loading": "Wrthi'n llwytho…",
  "common.tryAgain": "Rhowch gynnig arall arni",
  "common.somethingWentWrong": "Aeth rhywbeth o'i le. Rhowch gynnig arall arni.",
  "common.language": "Iaith",
  "common.changeLanguage": "Newid iaith",

  // --- Banners ----------------------------------------------------------------
  "banner.demo.title": "System arddangos.",
  "banner.demo.body":
    "Nid yw hon yn wasanaeth GIG. Data synthetig yn unig. Peidiwch â rhoi gwybodaeth wirioneddol am gleifion.",
  "banner.demo.emergency": "Mewn argyfwng ffoniwch 999.",

  // --- Navigation ---------------------------------------------------------------
  "nav.overview": "Trosolwg",
  "nav.symptomCheck": "Gwiriad symptomau",
  "nav.appointments": "Apwyntiadau",

  // --- Dashboard -----------------------------------------------------------------
  "dashboard.title": "Eich cyfrif",
  "dashboard.welcome": "Croeso yn ôl, {name}.",
  "dashboard.prompt.eyebrow": "Ddim yn siŵr beth sydd ei angen arnoch?",
  "dashboard.prompt.title": "Dywedwch wrthym sut rydych chi'n teimlo",
  "dashboard.prompt.body":
    "Disgrifiwch eich symptomau a byddwn yn eich helpu i ddod o hyd i'r apwyntiad iawn. Gwiriad awtomatig yw hwn, nid clinigwr, ac nid yw'n rhoi diagnosis.",
  "dashboard.prompt.action": "Dechrau gwiriad symptomau",
  "dashboard.details.title": "Eich manylion",
  "dashboard.details.name": "Enw",
  "dashboard.details.email": "Cyfeiriad e-bost",
  "dashboard.details.accountType": "Math o gyfrif",
  "dashboard.details.patient": "Claf",
  "dashboard.appointments.title": "Apwyntiadau",
  "dashboard.appointments.none": "Nid oes gennych apwyntiadau sydd i ddod.",
  "dashboard.appointments.next": "Eich apwyntiad nesaf",
  "dashboard.appointments.seeAll": "Gweld eich holl apwyntiadau",
  "dashboard.appointments.book": "Trefnu apwyntiad",

  // --- Symptom check ------------------------------------------------------------------
  "symptomCheck.title": "Gwiriad symptomau",
  "symptomCheck.intro":
    "Disgrifiwch sut rydych chi'n teimlo a byddwn yn eich helpu i ddod o hyd i'r apwyntiad iawn. Gwiriad awtomatig yw hwn, nid clinigwr, ac nid yw'n rhoi diagnosis.",
  "symptomCheck.emergencyBanner.title": "Os yw hyn yn argyfwng, ffoniwch 999 nawr",
  "symptomCheck.emergencyBanner.body":
    "Ni all y gwiriad hwn helpu mewn argyfwng. Am gyngor brys ffoniwch GIG 111.",
  "symptomCheck.start.title": "Dechrau gwiriad symptomau",
  "symptomCheck.start.body":
    "Byddwn yn gofyn ychydig o gwestiynau byr. Gallwch stopio ar unrhyw adeg.",
  "symptomCheck.start.action": "Dechrau",
  "symptomCheck.startAgain": "Dechrau eto",
  "symptomCheck.startNew": "Dechrau gwiriad newydd",
  "symptomCheck.restart.title": "Dechrau eto?",
  "symptomCheck.restart.body":
    "Bydd y gwiriad hwn yn cael ei ddileu a bydd un newydd yn dechrau. Ni fydd unrhyw beth rydych wedi'i deipio hyd yn hyn yn cael ei ddefnyddio i awgrymu apwyntiad.",
  "symptomCheck.restart.keepGoing": "Parhau",
  "symptomCheck.conversation": "Sgwrs",
  "symptomCheck.you": "Chi",
  "symptomCheck.automatedCheck": "Gwiriad awtomatig",
  "symptomCheck.reply.label": "Eich ateb",
  "symptomCheck.reply.hint":
    "Disgrifiwch bethau yn eich geiriau eich hun. Gallwch ddechrau eto ar unrhyw adeg.",
  "symptomCheck.reply.send": "Anfon",
  "symptomCheck.reply.sending": "Yn anfon",
  "symptomCheck.escalated.title": "Wedi'i drosglwyddo i aelod o staff",
  "symptomCheck.escalated.body":
    "Rydym wedi stopio gofyn cwestiynau. Bydd rhywun yn edrych ar hyn.",

  "symptomCheck.emergency.title": "Ffoniwch 999 nawr",
  "symptomCheck.emergency.body":
    "Mae'r hyn rydych wedi'i ddisgrifio angen help brys. Peidiwch ag aros am apwyntiad, a pheidiwch â gyrru eich hun.",
  "symptomCheck.emergency.call": "Ffonio 999",
  "symptomCheck.emergency.orAande": "Neu ewch i'ch adran achosion brys agosaf.",

  "symptomCheck.outcome.title": "Beth rydym yn ei awgrymu",
  "symptomCheck.outcome.seeAppointments": "Gweld apwyntiadau",
  "symptomCheck.outcome.notADiagnosis": "Nid diagnosis yw hwn.",
  "symptomCheck.outcome.ifWorse":
    "Os ydych yn teimlo'n waeth, ffoniwch GIG 111, neu 999 mewn argyfwng.",
  "symptomCheck.band.URGENT": "Cael eich gweld o fewn 24 awr",
  "symptomCheck.band.SOON": "Cael eich gweld o fewn wythnos",
  "symptomCheck.band.ROUTINE": "Apwyntiad arferol",
  "symptomCheck.band.SELF_CARE": "Hunanofal",

  // --- Appointments -------------------------------------------------------------------
  "appointments.title": "Eich apwyntiadau",
  "appointments.intro": "Trefnu, newid neu ganslo apwyntiad.",
  "appointments.book": "Trefnu apwyntiad",
  "appointments.includePast": "Cynnwys apwyntiadau blaenorol a rhai wedi'u canslo",
  "appointments.none.title": "Dim apwyntiadau",
  "appointments.none.upcoming": "Nid oes gennych apwyntiadau sydd i ddod.",
  "appointments.none.any": "Nid oes gennych apwyntiadau ar gofnod.",
  "appointments.reference": "Cyfeirnod",
  "appointments.youToldUs": "Dywedoch wrthym",
  "appointments.change": "Newid yr apwyntiad hwn",
  "appointments.cancel": "Canslo'r apwyntiad hwn",
  "appointments.booked.title": "Apwyntiad wedi'i drefnu",
  "appointments.status.BOOKED": "Wedi'i drefnu",
  "appointments.status.CANCELLED": "Wedi'i ganslo",
  "appointments.status.DID_NOT_ATTEND": "Heb fynychu",
  "appointments.cancelDialog.title": "Canslo'r apwyntiad hwn?",
  "appointments.cancelDialog.body":
    "Mae canslo yn rhyddhau'r amser hwn i rywun arall. Bydd angen i chi drefnu eto os oes angen i chi gael eich gweld o hyd.",
  "appointments.cancelDialog.confirm": "Ie, canslwch ef",
  "appointments.cancelDialog.keep": "Cadw'r apwyntiad hwn",
  "appointments.cancelDialog.cancelling": "Yn canslo",

  // --- Booking --------------------------------------------------------------------------
  "booking.title": "Trefnu apwyntiad",
  "booking.intro":
    "Dewiswch amser sy'n addas i chi. Byddwn yn ei gadw am bum munud tra byddwch yn cadarnhau.",
  "booking.backToAppointments": "Yn ôl i'ch apwyntiadau",
  "booking.department": "Adran",
  "booking.allDepartments": "Pob adran",
  "booking.loadingTimes": "Wrthi'n llwytho amseroedd…",
  "booking.none.title": "Dim apwyntiadau ar gael",
  "booking.none.body":
    "Nid oes amseroedd rhydd yn yr adran hon ar hyn o bryd. Rhowch gynnig ar adran arall, neu cysylltwch â'r ysbyty yn uniongyrchol.",
  "booking.held": "Wedi'i gadw i chi",
  "booking.confirm.title": "Cadarnhau eich apwyntiad",
  "booking.confirm.when": "Pryd",
  "booking.confirm.department": "Adran",
  "booking.confirm.clinician": "Clinigwr",
  "booking.confirm.toBeConfirmed": "I'w gadarnhau",
  "booking.confirm.action": "Cadarnhau'r apwyntiad hwn",
  "booking.confirm.booking": "Yn trefnu eich apwyntiad",
  "booking.confirm.chooseAnother": "Dewis amser gwahanol",
  "booking.conflict.title": "Dewiswch amser arall",

  // --- Authentication ----------------------------------------------------------------------
  "auth.signIn.title": "Mewngofnodi",
  "auth.signIn.email": "Cyfeiriad e-bost",
  "auth.signIn.password": "Cyfrinair",
  "auth.signIn.action": "Mewngofnodi",
  "auth.signIn.signingIn": "Yn mewngofnodi",
  "auth.signIn.failed": "Methu mewngofnodi",
  "auth.signIn.forgotten": "Rwyf wedi anghofio fy nghyfrinair",
  "auth.signIn.noAccount": "Dim cyfrif gennych?",
  "auth.signIn.createOne": "Crëwch un nawr",
};
