# Verification of held-out forecasts

Primary model (predeclared): **E4_lstm_tcn**, seed mean. Test period 2024-01-03 → 2026-03-11, 304375 samples.

## Skill by regime (MAE in mm; skill = improvement over zero-motion)

```
                    model  MAE_all  MAE_moving  MAE_stable  MAE_high  cov80  cov80_moving  cov80_high  skill_all_%  skill_moving_%  skill_stable_%  skill_high_%
              zero_motion    2.790       3.629       2.741    11.013    NaN           NaN         NaN        0.000           0.000           0.000         0.000
persistence_last_interval    4.721       6.151       4.638    15.064    NaN           NaN         NaN      -69.220         -69.513         -69.197       -36.779
 constant_velocity_window    3.042       3.922       2.990    11.585    NaN           NaN         NaN       -9.012          -8.093          -9.083        -5.186
             ridge_linear    2.503       3.312       2.455     8.802    NaN           NaN         NaN       10.307           8.726          10.429        20.079
                   E1_gru    2.466       3.267       2.419     8.708  0.771         0.710       0.092       11.624           9.961          11.753        20.929
                  E1b_mlp    2.498       3.331       2.450     8.693  0.750         0.690       0.109       10.453           8.207          10.626        21.067
                  E2_lstm    2.500       3.291       2.454     8.738  0.750         0.698       0.079       10.383           9.312          10.466        20.664
              E3_lstm_tcn    2.453       3.275       2.406     8.702  0.768         0.699       0.097       12.065           9.738          12.245        20.984
                  E3b_tcn    2.471       3.300       2.422     8.690  0.755         0.693       0.095       11.447           9.060          11.632        21.099
              E4_lstm_tcn    2.481       3.292       2.434     8.830  0.757         0.685       0.074       11.070           9.286          11.208        19.825
              E5_lstm_tcn    2.463       3.287       2.415     9.020  0.764         0.688       0.086       11.725           9.424          11.903        18.096
```

## Noise floor

```
{
 "zero_motion_MAE_stable_mm": 2.741210699081421,
 "stable_increment_std_mm": 3.798938274383545,
 "share_of_test_samples_stable": 0.9448739219712525,
 "primary_MAE_stable_mm": 2.4292054176330566
}
```

## Per-pixel

```
{
 "n_pixels": 5441,
 "share_pixels_model_better": 0.9404521227715493,
 "median_pixel_skill_pct": 11.428898811340332
}
```

## Most active pixel

```
{
 "pixel": [
  58,
  20
 ],
 "n": 49,
 "MAE_model": 8.516197204589844,
 "MAE_zero": 9.320356369018555,
 "cov80": 0.20408163265306123,
 "observed_total_mm": -59.602020263671875,
 "forecast_total_mm": 75.30767822265625
}
```

## Ground-truth coverage during the 2024 acceleration

```
{
 "valid_frac_moving_zone_2016_2022": 0.9539434924050307,
 "valid_frac_moving_zone_JunNov2024": 0.731934731934732,
 "valid_frac_all_JunNov2024": 0.7166844919786096,
 "max_measured_LOS_rate_JunNov2024_mm_day": 2.272263844807943,
 "p99_measured_LOS_rate_JunNov2024_mm_day": 1.8869347095489504,
 "published_JPL_UAVSAR_SepOct2024_mm_day": 14.5,
 "published_city_JulAug2024_mm_day": 43.5,
 "c_band_12day_unwrap_limit_note": "~lambda/4 = 14 mm of LOS change between neighbouring pixels per pair"
}
```