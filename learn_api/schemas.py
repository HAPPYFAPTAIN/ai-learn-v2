"""Response contracts for the React client; no additional business operations."""
from datetime import datetime
from typing import Any, Generic, TypeVar, Literal
from pydantic import BaseModel, model_validator

T = TypeVar("T")

class GenerationOut(BaseModel):
    jobId: str
    state: str

class ModelOptionOut(BaseModel):
    id: str
    provider: str

class ModelSelectionOut(BaseModel):
    selectedModel: str

class ModelCatalogOut(ModelSelectionOut):
    items: list[ModelOptionOut]
    selectedAvailable: bool
    source: Literal['personal', 'gateway'] = 'gateway'
    providerImportEnabled: bool = False

class ProviderOut(BaseModel):
    id: str
    provider: str
    name: str
    baseUrl: str
    models: list[str]
    remark: str = ''
    website: str = ''
    revision: str

class ProviderListOut(BaseModel):
    enabled: bool
    connections: list[ProviderOut]

class ProviderCreatedOut(BaseModel):
    connection: ProviderOut
    verifiedMs: int

class Items(BaseModel, Generic[T]):
    items: list[T]

class ProjectOut(BaseModel):
    id: int
    title: str
    topic: str
    background: str
    goal: str
    weeklyHours: float
    status: str
    createdAt: datetime
    updatedAt: datetime

class ProjectCreated(ProjectOut):
    generation: GenerationOut | None = None

class ProjectList(Items[ProjectOut]):
    limit: int
    offset: int

class NodeOut(BaseModel):
    id: int
    projectId: int
    code: str
    title: str
    description: str
    stage: str
    estHours: float
    difficulty: float
    mastery: float
    status: str
    contentVersion: int
    createdAt: datetime

class NoteOut(BaseModel):
    id: int
    projectId: int
    nodeId: int
    content: str
    selection: str
    updatedAt: datetime

class TaskOut(BaseModel):
    id: int
    projectId: int
    nodeId: int | None
    title: str
    description: str
    taskType: str
    status: str
    output: str

class CardOut(BaseModel):
    id: int
    projectId: int | None
    nodeId: int | None
    front: str
    back: str
    cardType: str
    state: int
    step: int
    reps: int
    stability: float
    nextReview: datetime | None
    suspended: bool

class QuestionOut(BaseModel):
    id: int
    qtype: str
    stem: str
    options: list[Any]
    difficulty: int

class QuizBrief(BaseModel):
    id: int
    title: str
    quizType: str
    createdAt: datetime

class QuizOut(BaseModel):
    id: int
    title: str
    quizType: str
    questions: list[QuestionOut]

class AnswerOut(BaseModel):
    questionId: int
    correct: bool
    expected: str
    explanation: str
    userAnswer: str = ""
    feedback: str = ""

class GradeOut(BaseModel):
    correct: int
    total: int
    score: float
    results: list[AnswerOut]

class MaterialOut(BaseModel):
    fileId: str
    name: str
    sizeBytes: int
    sha256: str
    createdAt: datetime

class MaterialPreviewOut(BaseModel):
    fileId: str
    name: str
    text: str
    truncated: bool

class UploadOut(BaseModel):
    fileId: str
    sha256: str
    sizeBytes: int
    jobId: str | None

class PlanItem(BaseModel):
    nodeId: int
    code: str
    title: str
    hours: float

class PlanWeek(BaseModel):
    index: int
    hours: float
    items: list[PlanItem]

class PlanOut(BaseModel):
    projectId: int
    weeks: list[PlanWeek]
    totalHours: float

class ReportOut(BaseModel):
    id: int
    date: str
    content: str
    studyMinutes: int
    cardsReviewed: int
    nodesProgressed: int

class SummaryOut(BaseModel):
    totalNodes: int
    nodesByStatus: dict[str, int]
    completedNodes: int
    completionRatio: float
    masteredNodes: int
    masteryRatio: float
    studyMinutes: float

class JobOut(BaseModel):
    jobId: str
    kind: str
    subject: str
    state: str
    progress: dict[str, Any]
    error: str | None
    updatedAt: datetime

class ChatOut(BaseModel):
    eventId: str
    content: str
    model: str
    usage: dict[str, Any]

class CitationOut(BaseModel):
    fileId: str
    name: str
    excerpt: str
    label: str

class ConversationMessageOut(BaseModel):
    truncated: bool = False
    role: str
    content: str
    references: list[CitationOut]
    createdAt: str

class ConversationOut(BaseModel):
    messages: list[ConversationMessageOut]
    activeJob: GenerationOut | None
    pendingQuestion: str | None

class MeOut(BaseModel):
    userId: str
    displayName: str
    capabilities: dict[str, bool]
    storage: dict[str, int] | None = None


class NonNullPatch(BaseModel):
    """PATCH may omit required DB columns, but may not explicitly null them."""
    @model_validator(mode='before')
    @classmethod
    def reject_null(cls, data):
        if isinstance(data, dict):
            for name, value in data.items():
                if value is None:
                    # Field-only error, never include submitted contents.
                    from pydantic import ValidationError
                    raise ValidationError.from_exception_data(cls.__name__, [
                        {'type': 'value_error', 'loc': (name,), 'input': None,
                         'ctx': {'error': ValueError('不能为空')}}])
        return data
