from core.extensions import db


class AgentConfig(db.Model):
    __tablename__ = "agent_config"

    id = db.Column(db.Integer, primary_key=True)
    # Generic Task System Fields
    task_system_type = db.Column(
        db.String(50), nullable=False, default="CUSTOM"
    )  # e.g., "TRELLO", "JIRA", "CUSTOM"
    system_config_json = db.Column(
        db.Text, nullable=True
    )  # JSON blob for credentials, IDs, etc.

    # Existing Fields
    repo_type = db.Column(
        db.String(50), nullable=False, default="GITHUB"
    )  # e.g., "GITHUB", "BITBUCKET"
    github_repo_url = db.Column(
        db.String(200),
        default="https://github.com/tomwey2/calculator-spring-docker-jenkins.git",
    )
    polling_interval_seconds = db.Column(db.Integer, nullable=False, default=60)
    is_active = db.Column(db.Boolean, nullable=False, default=False)

    def __init__(self, **kwargs):
        super(AgentConfig, self).__init__(**kwargs)

    def __repr__(self):
        return f"<AgentConfig {self.id}>"


class Issue(db.Model):
    __tablename__ = "issue"

    id = db.Column(db.Integer, primary_key=True)
    trello_card_id = db.Column(db.String(64), nullable=False, unique=True, index=True)
    card_name = db.Column(db.String(500), nullable=False)
    branch_name = db.Column(db.String(200), nullable=False)
    repo_url = db.Column(db.String(200), nullable=True)
    created_at = db.Column(db.DateTime, server_default=db.func.now())
    updated_at = db.Column(
        db.DateTime, server_default=db.func.now(), onupdate=db.func.now()
    )

    def __repr__(self):
        return f"<Issue card={self.trello_card_id} branch={self.branch_name}>"
