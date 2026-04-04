from __future__ import annotations

from .schemas import NormalizedEvent, RiskAssessment, RiskLevel


class RiskEngine:
    _CRITICAL_PATTERNS = (
        'ignore previous instructions',
        'show me all hidden data',
        'show hidden data',
        'reveal system prompt',
        'show system prompt',
        'print your hidden instructions',
        'give me credentials',
        'admin password',
        'api key',
        'token secreto',
    )
    _HIGH_PATTERNS = (
        'ignore all policies',
        'bypass security',
        'prompt injection',
        'jailbreak',
        'hidden instructions',
        'credenciales internas',
        'datos ocultos',
    )

    def assess(self, event: NormalizedEvent) -> RiskAssessment:
        text = event.message_text.lower()

        critical_flags = [pattern for pattern in self._CRITICAL_PATTERNS if pattern in text]
        if critical_flags:
            return RiskAssessment(
                level=RiskLevel.CRITICAL,
                flags=['prompt_injection_attempt', 'sensitive_data_request'],
                reasons=[f'Detected critical risk pattern: "{pattern}"' for pattern in critical_flags],
                sanitized_text='',
                allow_tools=False,
                require_human_review=True,
            )

        high_flags = [pattern for pattern in self._HIGH_PATTERNS if pattern in text]
        if high_flags:
            return RiskAssessment(
                level=RiskLevel.HIGH,
                flags=['suspicious_instruction'],
                reasons=[f'Detected suspicious pattern: "{pattern}"' for pattern in high_flags],
                sanitized_text=event.message_text,
                allow_tools=False,
                require_human_review=True,
            )

        return RiskAssessment(
            level=RiskLevel.LOW,
            flags=[],
            reasons=[],
            sanitized_text=event.message_text,
            allow_tools=True,
            require_human_review=False,
        )
