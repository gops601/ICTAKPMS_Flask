from app.extensions import db
from .base import TimestampMixin

TASK_STATUSES = ("backlog", "todo", "in_progress", "in_review", "completed")
TASK_PRIORITIES = ("low", "medium", "high", "critical")


class ScrumBoard(TimestampMixin, db.Model):
    __tablename__ = "scrum_boards"
    id = db.Column(db.Integer, primary_key=True)
    project_id = db.Column(db.Integer, db.ForeignKey("projects.id", ondelete="CASCADE"), unique=True, nullable=False)

    tasks = db.relationship("ScrumTask", back_populates="board", cascade="all, delete-orphan")


class ScrumTask(TimestampMixin, db.Model):
    __tablename__ = "scrum_tasks"
    id = db.Column(db.Integer, primary_key=True)
    board_id = db.Column(db.Integer, db.ForeignKey("scrum_boards.id", ondelete="CASCADE"), nullable=False, index=True)
    title = db.Column(db.String(255), nullable=False)
    description = db.Column(db.Text)
    assigned_student_id = db.Column(db.Integer, db.ForeignKey("students.id", ondelete="SET NULL"), index=True)
    created_by = db.Column(db.Integer, db.ForeignKey("users.id", ondelete="SET NULL"))
    priority = db.Column(db.String(10), default="medium", nullable=False)
    status = db.Column(db.String(15), default="backlog", nullable=False, index=True)
    position = db.Column(db.Integer, default=0, nullable=False)
    start_date = db.Column(db.Date)
    due_date = db.Column(db.Date, index=True)
    completed_at = db.Column(db.DateTime)
    is_archived = db.Column(db.Boolean, default=False, nullable=False)
    version = db.Column(db.Integer, default=1, nullable=False)

    board = db.relationship("ScrumBoard", back_populates="tasks")
    assignee = db.relationship("Student")
    comments = db.relationship("ScrumTaskComment", back_populates="task", cascade="all, delete-orphan")
    history = db.relationship("ScrumTaskHistory", back_populates="task", cascade="all, delete-orphan")


class ScrumTaskComment(TimestampMixin, db.Model):
    __tablename__ = "scrum_task_comments"
    id = db.Column(db.Integer, primary_key=True)
    task_id = db.Column(db.Integer, db.ForeignKey("scrum_tasks.id", ondelete="CASCADE"), nullable=False, index=True)
    user_id = db.Column(db.Integer, db.ForeignKey("users.id", ondelete="SET NULL"))
    body = db.Column(db.Text, nullable=False)

    task = db.relationship("ScrumTask", back_populates="comments")
    user = db.relationship("User")


class ScrumTaskHistory(db.Model):
    __tablename__ = "scrum_task_history"
    id = db.Column(db.Integer, primary_key=True)
    task_id = db.Column(db.Integer, db.ForeignKey("scrum_tasks.id", ondelete="CASCADE"), nullable=False, index=True)
    user_id = db.Column(db.Integer, db.ForeignKey("users.id", ondelete="SET NULL"))
    action = db.Column(db.String(40), nullable=False)
    field = db.Column(db.String(60))
    old_value = db.Column(db.String(500))
    new_value = db.Column(db.String(500))
    created_at = db.Column(db.DateTime, nullable=False)

    task = db.relationship("ScrumTask", back_populates="history")
