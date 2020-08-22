"""Override presets."""


OVERRIDE_PRESETS = {
    "imitation_optimizer": [
        (
            ["optimizer"],
            {"class_name": "rmsprop",
             "config": {"learning_rate": 0.001, "rho": 0.9}}
        ), (
            ["training", "imitation_optimizer"],
            {"class_name": "rmsprop",
             "config": {"learning_rate": 0.001, "rho": 0.9}}
        )
    ],
    "two_teachers": [
        (
            ["training", "teachers", "*"],
            {"class_name": "rmsprop",
             "config": {"learning_rate": 0.001, "rho": 0.9}}
        )
    ]
}


def get_preset(name):
    """Get preset override by name."""
    return OVERRIDE_PRESETS.get(name, [])