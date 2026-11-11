# Only SETTABLE fields belong here
SETTABLE_FIELD_TO_CAPABILITIY: dict[str,str] = {
    "on": "on_off",
    "brightness":"brightness",
    "color_xy": "color_xy",
    "color_temp_k": "color_temp_k",
    "target_temp_c": "target_temperature",
    "mode": "hvac_mode"
}

# the key in info tha tholds its min, max limits 
FIELD_TO_RANGE_KEY: dict[str,str] = {
    "color_temp_k": "color_temp_k_range",
    "target_temp_c": "target_temp_c_range"
}