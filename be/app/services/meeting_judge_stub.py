"""회의 발화 판단 모델 식별자 상수 (#135 → #141).

회의 판단 자체는 app.ai.judge_utterance로 이미 바뀌었다(#141). 여기 남은 상수는
① Discord 판단(#116, 아직 더미)의 POLICY_VERSION 조합과 ② 회의 판단이 AIError로
실패했을 때 ContextDecision에 채울 model_version/policy_version 자리표시용으로만
쓴다.
"""

STUB_MODEL_NAME = "stub-meeting-judge"
STUB_PROMPT_VERSION = "stub-v2"
