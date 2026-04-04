class InvariantEngine:
    def check(self, paper_exec: dict, live_exec: dict) -> list:
        violations = []

        if not paper_exec or not live_exec:
            return violations

        # 1️⃣ Position invariant
        if paper_exec.get("positions") != live_exec.get("positions"):
            violations.append({
                "code": "POSITION_MISMATCH",
                "severity": "CRITICAL",
                "paper": paper_exec.get("positions"),
                "live": live_exec.get("positions"),
            })

        # 2️⃣ Decision invariant
        if paper_exec.get("lastDecision") != live_exec.get("lastDecision"):
            violations.append({
                "code": "DECISION_MISMATCH",
                "severity": "WARN",
                "paper": paper_exec.get("lastDecision"),
                "live": live_exec.get("lastDecision"),
            })

        return violations
