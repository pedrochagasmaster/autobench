from core.preset_workflow import PresetWorkflow


def test_load_preset_data_returns_dict() -> None:
    workflow = PresetWorkflow()

    preset_data = workflow.load_preset_data("balanced_default")

    assert isinstance(preset_data, dict)
    assert preset_data["preset_name"] == "balanced_default"
