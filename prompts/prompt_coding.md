# TASK
Implement the following task:
Task: {{task.name}}
Description: {{task.description}}
{% if task_comments %}
# REVIEW COMMENTS
The Pull Request was rejected with the following review comments: 
NOTE: The task description shows the current implementation. 
The comments below indicate ADDITIONAL work that needs to be done.
{% for comment in task_comments %}
  - {{ comment.text }}
{% endfor %}
{% endif %}
{% if pr_review_message %}
# PULL REQUEST MESSAGE
{{ pr_review_message }}
{% endif %}
{% if plan %}
# SPECIFIC IMPLEMENTATION PLAN
You MUST follow these exact steps to complete the task:
{{plan}}
{% endif %}