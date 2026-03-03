# TASK
Analyze the following task:
Task: {{agent_task.task_name}}
Description: {{agent_task.task_description}}
{% if provider_task_comments %}
# REVIEW COMMENTS
The Pull Request was rejected with the following review comments: 
NOTE: The task description shows the current implementation. 
The comments below indicate ADDITIONAL work that needs to be done.
{% for comment in provider_task_comments %}
  - {{ comment.text }}
{% endfor %}
{% endif %}
{% if pr_review_message %}
# PULL REQUEST MESSAGE
{{ pr_review_message }}
{% endif %}
{% if agent_task.plan_content %}
# SPECIFIC IMPLEMENTATION PLAN
You MUST follow these exact steps to complete the task:
{{agent_task.plan_content}}
{% endif %}