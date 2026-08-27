/**
 * Required on every page by ASSUMPTIONS.md.
 *
 * This system is not NHS-approved, not DTAC-assessed, not clinically validated and holds
 * no real patient data. Anyone landing on a screen that looks like an NHS service must be
 * told that immediately - a demo mistaken for a real service is a patient safety problem,
 * not just a presentational one.
 */
export function NonClinicalBanner() {
  return (
    <div className="border-b-4 border-nhs-warm-yellow bg-[#fff9e6]">
      <div className="mx-auto max-w-5xl px-4 py-2 text-center text-sm text-nhs-black">
        <strong>Demonstration system.</strong> Not an NHS service. Contains synthetic data
        only. Do not enter real patient information.{" "}
        <span className="whitespace-nowrap">
          In an emergency call <strong>999</strong>.
        </span>
      </div>
    </div>
  );
}
