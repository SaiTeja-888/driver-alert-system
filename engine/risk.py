class RiskEngine:
    @staticmethod
    def calculate_attention_score(data, phone_detected):
        score = 100

        if data["eye_status"] == "NO FACE":
            score -= 25
        elif data["eye_status"] == "CLOSED":
            score -= 40

        if data["yawning"]:
            score -= 20

        if data["head_direction"] not in {"CENTER", "UNKNOWN"}:
            score -= 20

        if phone_detected:
            score -= 30

        return max(score, 0)

    @staticmethod
    def get_risk_level(score):
        if score >= 80:
            return "LOW"
        if score >= 60:
            return "MEDIUM"
        if score >= 40:
            return "HIGH"
        return "CRITICAL"

risk_engine = RiskEngine()
