# TASK
Analyze the following task:
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
# IMPLEMENTATION PLAN
The following plan needs to be revised:
{{plan}}
{% endif %}