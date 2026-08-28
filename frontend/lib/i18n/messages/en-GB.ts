/**
 * English (en-GB) message catalogue - the authoritative source.
 *
 * This file defines the key set: every other locale is typed as a partial of it, so a key
 * that exists nowhere here cannot be translated, and a stale key in a translation is a
 * compile error rather than dead text nobody notices.
 *
 * Keys are grouped by screen. `{placeholders}` are substituted at render time.
 *
 * Keys listed in SAFETY_CRITICAL_KEYS carry advice that changes what someone does about
 * their health. In a DRAFT locale those render with the English alongside the translation -
 * see SafetyText.
 */

export const messages = {
  // --- Shared ---------------------------------------------------------------
  "common.serviceName": "NHS Digital Hospital Agent",
  "common.signOut": "Sign out",
  "common.signedInAs": "Signed in as {name}",
  "common.back": "Back",
  "common.cancel": "Cancel",
  "common.loading": "Loading…",
  "common.tryAgain": "Try again",
  "common.somethingWentWrong": "Something went wrong. Please try again.",
  "common.language": "Language",
  "common.changeLanguage": "Change language",

  // --- Demonstration and safety banners ---------------------------------------
  "banner.demo.title": "Demonstration system.",
  "banner.demo.body":
    "Not an NHS service. Contains synthetic data only. Do not enter real patient information.",
  "banner.demo.emergency": "In an emergency call 999.",
  "banner.draftTranslation.title": "These translations have not been checked",
  "banner.draftTranslation.body":
    "This page has been translated automatically. It has not been checked by a professional translator or a clinician. Anything that affects your care is also shown in English.",

  // --- Navigation --------------------------------------------------------------
  "nav.overview": "Overview",
  "nav.symptomCheck": "Symptom check",
  "nav.appointments": "Appointments",

  // --- Dashboard ----------------------------------------------------------------
  "dashboard.title": "Your account",
  "dashboard.welcome": "Welcome back, {name}.",
  "dashboard.prompt.eyebrow": "Not sure what you need?",
  "dashboard.prompt.title": "Tell us how you are feeling",
  "dashboard.prompt.body":
    "Describe your symptoms and we will help you find the right appointment. This is an automated check, not a clinician, and it does not diagnose.",
  "dashboard.prompt.action": "Start symptom check",
  "dashboard.details.title": "Your details",
  "dashboard.details.name": "Name",
  "dashboard.details.email": "Email address",
  "dashboard.details.accountType": "Account type",
  "dashboard.details.patient": "Patient",
  "dashboard.appointments.title": "Appointments",
  "dashboard.appointments.none": "You have no upcoming appointments.",
  "dashboard.appointments.next": "Your next appointment",
  "dashboard.appointments.seeAll": "See all your appointments",
  "dashboard.appointments.book": "Book an appointment",

  // --- Symptom check ---------------------------------------------------------------
  "symptomCheck.title": "Symptom check",
  "symptomCheck.intro":
    "Describe how you are feeling and we will help you find the right appointment. This is an automated check, not a clinician, and it does not diagnose.",
  "symptomCheck.emergencyBanner.title": "If this is an emergency, call 999 now",
  "symptomCheck.emergencyBanner.body":
    "This check cannot help in an emergency. For urgent advice call NHS 111.",
  "symptomCheck.start.title": "Start a symptom check",
  "symptomCheck.start.body": "We will ask a few short questions. You can stop at any time.",
  "symptomCheck.start.action": "Start",
  "symptomCheck.startAgain": "Start again",
  "symptomCheck.startNew": "Start a new check",
  "symptomCheck.restart.title": "Start again?",
  "symptomCheck.restart.body":
    "This check will be discarded and a new one started. Nothing you have typed so far will be used to suggest an appointment.",
  "symptomCheck.restart.keepGoing": "Keep going",
  "symptomCheck.conversation": "Conversation",
  "symptomCheck.you": "You",
  "symptomCheck.automatedCheck": "Automated check",
  "symptomCheck.reply.label": "Your reply",
  "symptomCheck.reply.hint":
    "Describe things in your own words. You can start again at any point.",
  "symptomCheck.reply.send": "Send",
  "symptomCheck.reply.sending": "Sending",
  "symptomCheck.escalated.title": "Passed to a member of staff",
  "symptomCheck.escalated.body":
    "We have stopped asking questions. Someone will look at this.",

  // Safety-critical: these change what someone does about their health.
  "symptomCheck.emergency.title": "Call 999 now",
  "symptomCheck.emergency.body":
    "What you have described needs emergency help. Do not wait for an appointment, and do not drive yourself.",
  "symptomCheck.emergency.call": "Call 999",
  "symptomCheck.emergency.orAande": "Or go to your nearest A&E.",

  "symptomCheck.outcome.title": "What we suggest",
  "symptomCheck.outcome.seeAppointments": "See appointments",
  "symptomCheck.outcome.notADiagnosis": "This is not a diagnosis.",
  "symptomCheck.outcome.producedBy":
    "It is an automated suggestion to help you choose an appointment, produced by {engine}. A clinician has not yet reviewed it.",
  "symptomCheck.outcome.ifWorse":
    "If you feel worse, call NHS 111, or 999 in an emergency.",
  "symptomCheck.band.URGENT": "Be seen within 24 hours",
  "symptomCheck.band.SOON": "Be seen within a week",
  "symptomCheck.band.ROUTINE": "A routine appointment",
  "symptomCheck.band.SELF_CARE": "Self care",

  // --- Appointments -----------------------------------------------------------------
  "appointments.title": "Your appointments",
  "appointments.intro": "Book, change or cancel an appointment.",
  "appointments.book": "Book an appointment",
  "appointments.includePast": "Include past and cancelled appointments",
  "appointments.none.title": "No appointments",
  "appointments.none.upcoming": "You have no upcoming appointments.",
  "appointments.none.any": "You have no appointments on record.",
  "appointments.reference": "Reference",
  "appointments.youToldUs": "You told us",
  "appointments.change": "Change this appointment",
  "appointments.cancel": "Cancel this appointment",
  "appointments.booked.title": "Appointment booked",
  "appointments.booked.body":
    "Your reference is {reference}. We have sent a confirmation to your email address.",
  "appointments.status.BOOKED": "Booked",
  "appointments.status.CANCELLED": "Cancelled",
  "appointments.status.DID_NOT_ATTEND": "Not attended",
  "appointments.cancelDialog.title": "Cancel this appointment?",
  "appointments.cancelDialog.body":
    "Cancelling frees this time for someone else. You will need to book again if you still need to be seen.",
  "appointments.cancelDialog.confirm": "Yes, cancel it",
  "appointments.cancelDialog.keep": "Keep this appointment",
  "appointments.cancelDialog.cancelling": "Cancelling",

  // --- Booking ------------------------------------------------------------------------
  "booking.title": "Book an appointment",
  "booking.intro": "Choose a time that suits you. We hold it for five minutes while you confirm.",
  "booking.backToAppointments": "Back to your appointments",
  "booking.department": "Department",
  "booking.allDepartments": "All departments",
  "booking.loadingTimes": "Loading available times…",
  "booking.none.title": "No appointments available",
  "booking.none.body":
    "There are no free times in this department at the moment. Try another department, or contact the hospital directly.",
  "booking.held": "Held for you",
  "booking.confirm.title": "Confirm your appointment",
  "booking.confirm.when": "When",
  "booking.confirm.department": "Department",
  "booking.confirm.clinician": "Clinician",
  "booking.confirm.toBeConfirmed": "To be confirmed",
  "booking.confirm.holding":
    "We are holding this time for {countdown}. If someone books it first we will tell you and nothing will be booked.",
  "booking.confirm.action": "Confirm this appointment",
  "booking.confirm.booking": "Booking your appointment",
  "booking.confirm.chooseAnother": "Choose a different time",
  "booking.conflict.title": "Please choose another time",

  // --- Authentication --------------------------------------------------------------------
  "auth.signIn.title": "Sign in",
  "auth.signIn.email": "Email address",
  "auth.signIn.password": "Password",
  "auth.signIn.action": "Sign in",
  "auth.signIn.signingIn": "Signing in",
  "auth.signIn.failed": "Could not sign in",
  "auth.signIn.forgotten": "I have forgotten my password",
  "auth.signIn.noAccount": "Do not have an account?",
  "auth.signIn.createOne": "Create one now",
} as const;

export type MessageKey = keyof typeof messages;

/**
 * Keys carrying advice that changes what someone does about their health.
 *
 * In a DRAFT locale these render with the authoritative English alongside the translation,
 * so nobody acts on wording that has not been checked. Adding a key here is cheap; leaving
 * one out is the expensive mistake.
 */
export const SAFETY_CRITICAL_KEYS: ReadonlySet<MessageKey> = new Set([
  "banner.demo.emergency",
  "symptomCheck.emergencyBanner.title",
  "symptomCheck.emergencyBanner.body",
  "symptomCheck.emergency.title",
  "symptomCheck.emergency.body",
  "symptomCheck.emergency.call",
  "symptomCheck.emergency.orAande",
  "symptomCheck.outcome.notADiagnosis",
  "symptomCheck.outcome.producedBy",
  "symptomCheck.outcome.ifWorse",
  "symptomCheck.band.URGENT",
  "symptomCheck.band.SOON",
  "symptomCheck.band.ROUTINE",
  "symptomCheck.band.SELF_CARE",
  "symptomCheck.escalated.body",
]);
