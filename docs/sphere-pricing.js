/**
 * sphere-pricing.js
 *
 * Copied unchanged from the Sphere Stand Generator (~/Code/3d_prints/js/
 * pricing.js). It has no imports and no DOM, so it is reused rather than
 * ported -- there is nothing here to keep in step with a generator.
 * Dual pricing estimation module for a 3D printing application.
 *
 * Two models are provided:
 *   1. calculateAggregatorEstimate  — models print-on-demand marketplace pricing
 *   2. calculateLocalPrintEstimate  — models local FDM printing on a high-speed CoreXY printer
 */

/** Minimum advertised price for any non-ABS aggregator order. */
const MIN_PRICE = 3.04;

/**
 * Total job volume threshold (cm³) below which non-ABS orders are anchored
 * to MIN_PRICE as a promotional floor rather than applying the raw formula.
 */
const SMALL_ORDER_THRESHOLD_CM3 = 4.0;

const IN3_TO_MM3 = 16387.064;

// Aggregator material coefficients reverse-engineered from marketplace data.
const materialProfiles = {
    'PLA':             { baseSetupFee: 0.75, volumetricMultiplier: 2.85 },
    'PLA+':            { baseSetupFee: 0.75, volumetricMultiplier: 2.85 },
    'RPLA':            { baseSetupFee: 0.75, volumetricMultiplier: 2.85 },
    'PETG':            { baseSetupFee: 0.75, volumetricMultiplier: 3.40 },
    'ABS':             { baseSetupFee: 0.75, volumetricMultiplier: 3.30 },
    'fallback_default':{ baseSetupFee: 0.75, volumetricMultiplier: 2.85 },
};

// Filament densities in g/cm³ for local print weight estimation.
const materialDensities = {
    'PLA':             1.24,
    'PLA+':            1.24,
    'RPLA':            1.24,
    'PETG':            1.27,
    'ABS':             1.04,
    'fallback_default':1.24,
};

/**
 * Converts cubic inches to cubic millimeters.
 * @param {number} cubicInches - Volume in in³.
 * @returns {number} Equivalent volume in mm³.
 */
export function cubeInchesToMm3(cubicInches) {
    return cubicInches * IN3_TO_MM3;
}

/**
 * Estimates the cost of a print-on-demand marketplace order.
 *
 * Uses cube-root volumetric scaling to simulate the bulk economies of scale
 * achieved when vendors nest multiple parts into a single build plate job.
 * Pricing is strictly volume-driven — mesh complexity, poly count, and text
 * geometry never affect the estimate.
 *
 * @param {string} material             - Material key ('PLA', 'PLA+', 'RPLA', 'PETG', 'ABS').
 *                                        Unknown materials fall back to the PLA profile.
 * @param {number} quantity             - Number of parts. Must be > 0.
 * @param {number} singlePartVolumeMm3  - Volume of one part in mm³. Must be > 0.
 * @returns {number} Estimated cost in USD, rounded to two decimal places.
 * @throws {Error} If quantity or singlePartVolumeMm3 are not positive numbers.
 */
export function calculateAggregatorEstimate(material, quantity, singlePartVolumeMm3) {
    if (!Number.isFinite(quantity) || quantity <= 0) {
        throw new Error(`quantity must be a positive number, got: ${quantity}`);
    }
    if (!Number.isFinite(singlePartVolumeMm3) || singlePartVolumeMm3 <= 0) {
        throw new Error(`singlePartVolumeMm3 must be a positive number, got: ${singlePartVolumeMm3}`);
    }

    const profile        = materialProfiles[material] ?? materialProfiles['fallback_default'];
    const totalVolumeCm3 = (singlePartVolumeMm3 / 1000) * quantity;

    // Small-order promotional floor: for non-ABS jobs under 4 cm³, anchor to
    // MIN_PRICE rather than applying the raw formula.
    if (material !== 'ABS' && totalVolumeCm3 < SMALL_ORDER_THRESHOLD_CM3) {
        return MIN_PRICE;
    }

    const rawPrice = profile.baseSetupFee + profile.volumetricMultiplier * Math.cbrt(totalVolumeCm3);
    return Math.round(Math.max(MIN_PRICE, rawPrice) * 100) / 100;
}

/** @deprecated Use calculateAggregatorEstimate instead. */
export const calculateEstimatedPrice = calculateAggregatorEstimate;

/**
 * Estimates the cost, print time, and filament weight for a local FDM print job
 * on a high-speed CoreXY printer (e.g. Bambu Lab P2S).
 *
 * Weight is modelled with a power law (W = 1.03 · V^0.8) because FDM parts are
 * mostly hollow: small parts are shell-dominated (higher effective density) while
 * large parts are infill-dominated (lower effective density).
 *
 * Print time uses a linear regression on weight (T = 71·W + 153 per part) that
 * accounts for perimeter slow-downs (the 153 s overhead) vs. bulk volumetric flow.
 * A fixed 476 s calibration penalty is applied once per job batch.
 *
 * @param {string} material              - Material key ('PLA', 'PLA+', 'RPLA', 'PETG', 'ABS').
 * @param {number} singlePartVolumeMm3   - Volume of one part in mm³. Must be > 0.
 * @param {number} quantity              - Number of parts. Must be > 0.
 * @param {number} [filamentCostPerKg=20.00] - Filament cost in USD per kg.
 * @returns {{ estimatedCostUsd: number, estimatedTimeHours: number, totalWeightGrams: number }}
 * @throws {Error} If quantity or singlePartVolumeMm3 are not positive numbers.
 */
export function calculateLocalPrintEstimate(material, singlePartVolumeMm3, quantity, filamentCostPerKg = 20.00) {
    if (!Number.isFinite(quantity) || quantity <= 0) {
        throw new Error(`quantity must be a positive number, got: ${quantity}`);
    }
    if (!Number.isFinite(singlePartVolumeMm3) || singlePartVolumeMm3 <= 0) {
        throw new Error(`singlePartVolumeMm3 must be a positive number, got: ${singlePartVolumeMm3}`);
    }

    const density      = materialDensities[material] ?? materialDensities['fallback_default'];
    const densityRatio = density / 1.24;

    const singleVolumeCm3    = singlePartVolumeMm3 / 1000.0;
    const singleWeightGrams  = (1.03 * Math.pow(singleVolumeCm3, 0.8)) * densityRatio;
    const totalWeightGrams   = singleWeightGrams * quantity;

    const materialCost = (totalWeightGrams / 1000.0) * filamentCostPerKg;

    const singlePartPrintSeconds = (71.0 * singleWeightGrams) + 153.0;
    const totalTimeSeconds       = 476.0 + (singlePartPrintSeconds * quantity);
    const totalTimeHours         = totalTimeSeconds / 3600.0;

    const electricityCost = 0.15 * totalTimeHours * 0.13;

    const estimatedCostUsd = materialCost + electricityCost;

    return {
        estimatedCostUsd:   Math.round(estimatedCostUsd  * 100) / 100,
        estimatedTimeHours: Math.round(totalTimeHours     * 100) / 100,
        totalWeightGrams:   Math.round(totalWeightGrams   * 100) / 100,
    };
}
