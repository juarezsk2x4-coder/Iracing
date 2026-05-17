"""Unit tests for weakness ranking and root-cause classification."""
from iracing_analyzer.ranking import RootCause, Weakness
from iracing_analyzer.root_cause import HardwareInfo, classify_weaknesses


def _hi(wheel_torque=18.0, pedals_type="hydraulic"):
    return HardwareInfo(
        wheel_model="Simagic Alpha Ultimate",
        wheel_torque_nm=wheel_torque,
        pedals_model="Simagic P2000",
        pedals_type=pedals_type,
        has_rig=True,
    )


def test_dd_wheel_jitter_classified_as_settings():
    w = Weakness(
        key="steering_jitter",
        name="Jitter",
        metric_value=0.04,
        metric_unit="rad",
        lap_time_cost_s=0.1,
        cost_math="",
        channels_used=["SteeringWheelAngle"],
        inference_flag=None,
    )
    classify_weaknesses([w], _hi(wheel_torque=18.0))
    assert w.root_cause == RootCause.SETTINGS


def test_belt_wheel_jitter_classified_as_hardware():
    w = Weakness(
        key="steering_jitter",
        name="Jitter",
        metric_value=0.04,
        metric_unit="rad",
        lap_time_cost_s=0.1,
        cost_math="",
        channels_used=["SteeringWheelAngle"],
        inference_flag=None,
    )
    classify_weaknesses([w], _hi(wheel_torque=2.5))
    assert w.root_cause == RootCause.HARDWARE


def test_hydraulic_brake_cv_classified_as_technique():
    w = Weakness(
        key="brake_cv",
        name="CV",
        metric_value=0.12,
        metric_unit="cv",
        lap_time_cost_s=0.1,
        cost_math="",
        channels_used=["Brake"],
        inference_flag=None,
    )
    classify_weaknesses([w], _hi(pedals_type="hydraulic"))
    assert w.root_cause == RootCause.TECHNIQUE


def test_potentiometer_brake_cv_classified_as_hardware():
    w = Weakness(
        key="brake_cv",
        name="CV",
        metric_value=0.12,
        metric_unit="cv",
        lap_time_cost_s=0.1,
        cost_math="",
        channels_used=["Brake"],
        inference_flag=None,
    )
    classify_weaknesses([w], _hi(pedals_type="potentiometer"))
    assert w.root_cause == RootCause.HARDWARE


def test_missing_channel_classified_as_ambiguous():
    w = Weakness(
        key="trail_braking",
        name="Trail",
        metric_value="n/a",
        metric_unit="",
        lap_time_cost_s=0.0,
        cost_math="",
        channels_used=["Brake"],
        inference_flag="SteeringWheelAngle missing",
    )
    classify_weaknesses([w], _hi())
    assert w.root_cause == RootCause.AMBIGUOUS
