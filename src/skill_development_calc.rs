use itertools::{izip, Itertools};
use pyo3::prelude::*;

mod calc_rating {
    fn erfc(x: f32) -> f32 {
        libm::erfc(x as f64) as f32
    }

    fn is_rating_okay(rating: f32, ssrs: &[f32], delta_multiplier: f32) -> bool {
        let max_power_sum: f64 = 2f64.powf(rating as f64 * 0.1);

        let power_sum: f64 = ssrs
            .iter()
            .map(|&ssr| (2.0 / erfc(delta_multiplier * (ssr - rating)) - 2.0) as f64)
            .filter(|&x| x > 0.0)
            .sum();

        power_sum < max_power_sum
    }

    /*
    The idea is the following: we try out potential skillset rating values
    until we've found the lowest rating that still fits (I've called that
    property 'okay'-ness in the code).
    How do we know whether a potential skillset rating fits? We give each
    score a "power level", which is larger when the skillset rating of the
    specific score is high. Therefore, the user's best scores get the
    highest power levels.
    Now, we sum the power levels of each score and check whether that sum
    is below a certain limit. If it is still under the limit, the rating
    fits (is 'okay'), and we can try a higher rating. If the sum is above
    the limit, the rating doesn't fit, and we need to try out a lower
    rating.
    */

    pub fn calc_rating(ssrs: &[f32], final_multiplier: f32, delta_multiplier: f32) -> f32 {
        let mut rating: f32 = 0.0;
        let mut resolution: f32 = 10.24;

        // Repeatedly approximate the final rating, with better resolution
        // each time
        while resolution > 0.01 {
            // Find lowest 'okay' rating with certain resolution
            while !is_rating_okay(rating + resolution, ssrs, delta_multiplier) {
                rating += resolution;
            }

            // Now, repeat with smaller resolution for better approximation
            resolution /= 2.0;
        }

        // Always be ever so slightly above the target value instead of below
        rating += resolution * 2.0;

        rating * final_multiplier
    }

    /// Basically a 1-to-1 replication of the MinaCalc `aggregate_skill` function.
    /// # Arguments
    /// * `v` - SSR values.
    /// * `delta_multiplier` - Not entirely sure what exactly this value does but its value is
    /// different based on the task it is used for.
    /// * `result_multiplier` - The final multiplier performed on the resulting rating value.
    /// * `rating` - A starting value of the rating, defaults to 0.0f32.
    /// * `resolution` - Part of the binary search algorithm, defaults to 10.24f32.
    pub fn aggregate_skill(
        v: &[&f32],
        delta_multiplier: f64,
        result_multiplier: f32,
        rating: Option<f32>,
        resolution: Option<f32>,
    ) -> f32 {
        let mut rating: f32 = rating.unwrap_or(0.0f32);
        let mut resolution: f32 = resolution.unwrap_or(10.24f32);
        // This algorithm is roughly a binary search, 11 iterations is enough to satisfy.
        for _i in 0..12 {
            let mut sum: f64;

            // Perform at least 1 repeat iteration of:
            // 1. Accumulate a sum of the input values after applying a function to the values
            //    initially.
            // 2. When threshold is reached, this iteration of the search concludes.
            loop {
                rating += resolution;
                sum = 0.0f64;
                for &vv in v.iter() {
                    let power_rating: f64 =
                        2.0f64 / libm::erfc(delta_multiplier * (vv - rating) as f64);
                    sum += f64::max(0.0f64, power_rating - 2.0f64);
                }

                if 2f64.powf(rating as f64 * 0.1) >= sum {
                    break;
                }
            }

            // Binary search: Move backwards and proceed half as quickly.
            rating -= resolution;
            resolution /= 2.0f32;
        }
        rating += resolution * 2.0f32;
        rating * result_multiplier
    }
}

#[pyclass]
pub struct SkillTimeline {
    #[pyo3(get)]
    pub rating_vectors: [Vec<f32>; 7],

    #[pyo3(get)]
    pub overall_ratings: Vec<f32>,
}

#[pymethods]
impl SkillTimeline {
    #[new]
    // used to be: pub fn create(ssr_vectors: [&[f32]; 7], day_ids: &[u64]) -> Self {

    /// Instantiates the SkillTimeline object with a 2D array of sessions and SSRs
    /// # Arguments
    /// * `ssr_vectors` - A 2D Vec with the outer index being the sessions and the inner index
    /// being the skillset category.
    /// * `day_ids` - A Vec of session IDs.
    /// # Example
    /// ```py
    /// ssr_lists = [[], [], [], [], [], [], []]
    /// # Populate the ssr_lists
    /// ...
    /// timeline = SkillTimeline(ssr_lists, list(range(len(ssr_lists))))
    /// ```
    pub fn create(ssr_vectors: Vec<Vec<f32>>, day_ids: Vec<u64>) -> Self {
        let mut rating_vectors: [Vec<f32>; 7] =
            [vec![], vec![], vec![], vec![], vec![], vec![], vec![]];
        let mut index = 0;
        for (_day_id, day_ids) in &day_ids.iter().group_by(|&&x| x) {
            index += day_ids.count();
            for (i, ssr_vector) in ssr_vectors.iter().enumerate() {
                //rating_vectors[i].push(calc_rating::calc_rating(&ssr_vector[..index], 1.11, 0.25));
                let skill_vector: Vec<_> = ssr_vector.iter().collect();
                rating_vectors[i].push(calc_rating::aggregate_skill(
                    &skill_vector[..index],
                    0.1f64,
                    1.05f32,
                    None,
                    None,
                ));
            }
        }
        let overall_ratings: Vec<f32> = izip!(
            &rating_vectors[0],
            &rating_vectors[1],
            &rating_vectors[2],
            &rating_vectors[3],
            &rating_vectors[4],
            &rating_vectors[5],
            &rating_vectors[6]
        )
        .map(|session_tuple| {
            let session_array: [&f32; 7] = session_tuple.into();
            calc_rating::aggregate_skill(&session_array, 0.1f64, 1.125f32, None, None)
        })
        .collect();

        SkillTimeline {
            rating_vectors,
            overall_ratings,
        }
    }
}
