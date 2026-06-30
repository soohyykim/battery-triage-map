def check_designated_waste(battery_info: dict) -> dict:
    """
    Rule Engine: 지정폐기물 여부 판정 (rule.py)
    
    입력:
    - flooded (bool): 침수
    - leakage (bool): 누액
    - overheated (bool): 과열
    - swollen (bool): 팽창
    - impact (bool): 충격
    
    로직:
    - 위 5항목 중 1개 이상 True → 지정폐기물 (Red)
    - 모두 False → 정상 (rule.py 통과 → triage.py로)
    """
    
    condition_flags = battery_info.get("condition_flags", {})
    
    risk_items = [
        condition_flags.get("flooded", False),
        condition_flags.get("leakage", False),
        condition_flags.get("overheated", False),
        condition_flags.get("swollen", False),
        condition_flags.get("impact", False)
    ]
    
    is_designated_waste = any(risk_items)  # 1개 이상 True면 True
    
    return {
        "status": "rule_checked",
        "is_designated_waste": is_designated_waste,
        "risk_flags": {
            "flooded": condition_flags.get("flooded", False),
            "leakage": condition_flags.get("leakage", False),
            "overheated": condition_flags.get("overheated", False),
            "swollen": condition_flags.get("swollen", False),
            "impact": condition_flags.get("impact", False)
        },
        "reason_codes": [
            "DESIGNATED_WASTE" if is_designated_waste else "NORMAL"
        ]
    }