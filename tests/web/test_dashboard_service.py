"""Tests for dashboard service functionality."""

from __future__ import annotations

import pytest
from unittest.mock import patch

from app.core.localdb.models import AgentTask
from app.web.services.dashboard_service import (
    PlanReviewError,
    _validate_plan_review_input,
    _rollback_task_state,
    process_plan_review,
)


class TestValidatePlanReviewInput:
    """Tests for _validate_plan_review_input function."""

    def test_valid_approved_state(self):
        """Should accept valid 'approved' state."""
        result = _validate_plan_review_input("approved", None)
        assert result == "approved"

    def test_valid_rejected_state_with_reason(self):
        """Should accept valid 'rejected' state with reason."""
        result = _validate_plan_review_input("rejected", "Test reason")
        assert result == "rejected"

    def test_case_insensitive_state(self):
        """Should handle case-insensitive state input."""
        result = _validate_plan_review_input("APPROVED", None)
        assert result == "approved"

    def test_whitespace_trimming(self):
        """Should trim whitespace from state input."""
        result = _validate_plan_review_input("  rejected  ", "  test reason  ")
        assert result == "rejected"

    def test_none_state_raises_error(self):
        """Should raise error for None state."""
        with pytest.raises(PlanReviewError, match="Plan state is required"):
            _validate_plan_review_input(None, None)

    def test_empty_state_raises_error(self):
        """Should raise error for empty state."""
        with pytest.raises(PlanReviewError, match="Plan state is required"):
            _validate_plan_review_input("", None)

    def test_non_string_state_raises_error(self):
        """Should raise error for non-string state."""
        with pytest.raises(PlanReviewError, match="must be a string"):
            _validate_plan_review_input(123, None)

    def test_invalid_state_raises_error(self):
        """Should raise error for invalid state."""
        with pytest.raises(PlanReviewError, match="Invalid state"):
            _validate_plan_review_input("invalid", None)

    def test_rejected_without_reason_raises_error(self):
        """Should raise error for rejected state without reason."""
        with pytest.raises(PlanReviewError, match="rejection reason is required"):
            _validate_plan_review_input("rejected", "")

    def test_rejected_with_whitespace_only_reason_raises_error(self):
        """Should raise error for rejected state with whitespace-only reason."""
        with pytest.raises(PlanReviewError, match="rejection reason is required"):
            _validate_plan_review_input("rejected", "   ")


class TestRollbackTaskState:
    """Tests for _rollback_task_state function."""

    @patch("app.web.services.dashboard_service.update_db_task")
    def test_successful_rollback(self, mock_update):
        """Should return True on successful rollback."""
        mock_update.return_value = AgentTask(task_id="test-123", plan_state="created")
        
        result = _rollback_task_state("test-123", "created")
        
        assert result is True
        mock_update.assert_called_once_with("test-123", plan_state="created")

    @patch("app.web.services.dashboard_service.update_db_task")
    def test_failed_rollback_returns_false(self, mock_update):
        """Should return False when rollback fails."""
        mock_update.return_value = None
        
        result = _rollback_task_state("test-123", "created")
        
        assert result is False

    @patch("app.web.services.dashboard_service.update_db_task")
    def test_rollback_with_exception_returns_false(self, mock_update):
        """Should return False when rollback raises exception."""
        mock_update.side_effect = ValueError("Database error")
        
        result = _rollback_task_state("test-123", "created")
        
        assert result is False


class TestProcessPlanReview:
    """Tests for process_plan_review function."""

    @patch("app.web.services.dashboard_service.move_task_to_in_progress")
    @patch("app.web.services.dashboard_service.add_plan_rejection_comment")
    @patch("app.web.services.dashboard_service.update_db_task")
    @patch("app.web.services.dashboard_service.read_db_task")
    @pytest.mark.asyncio
    async def test_successful_approval(self, mock_read, mock_update, mock_comment, mock_move):
        """Should handle successful plan approval."""
        # Setup
        mock_task = AgentTask(task_id="test-123", plan_state="created")
        mock_read.return_value = mock_task
        mock_updated = AgentTask(task_id="test-123", plan_state="approved")
        mock_update.return_value = mock_updated
        mock_move.return_value = True

        # Execute
        result = await process_plan_review("approved", None)

        # Verify
        assert result["message"] == "Plan state updated to approved"
        assert result["task_id"] == "test-123"
        assert result["plan_state"] == "approved"
        mock_update.assert_called_once_with("test-123", plan_state="approved")
        mock_move.assert_called_once_with("test-123")
        mock_comment.assert_not_called()

    @patch("app.web.services.dashboard_service.move_task_to_in_progress")
    @patch("app.web.services.dashboard_service.add_plan_rejection_comment")
    @patch("app.web.services.dashboard_service.update_db_task")
    @patch("app.web.services.dashboard_service.read_db_task")
    @pytest.mark.asyncio
    async def test_successful_rejection_with_comment(self, mock_read, mock_update, mock_comment, mock_move):
        """Should handle successful plan rejection with comment."""
        # Setup
        mock_task = AgentTask(task_id="test-123", plan_state="created")
        mock_read.return_value = mock_task
        mock_updated = AgentTask(task_id="test-123", plan_state="rejected")
        mock_update.return_value = mock_updated
        mock_comment.return_value = None
        mock_move.return_value = True

        # Execute
        result = await process_plan_review("rejected", "Test rejection reason")

        # Verify
        assert result["message"] == "Plan state updated to rejected"
        assert result["task_id"] == "test-123"
        assert result["plan_state"] == "rejected"
        mock_update.assert_called_once_with("test-123", plan_state="rejected")
        mock_comment.assert_called_once_with("test-123", "Test rejection reason")
        mock_move.assert_called_once_with("test-123")

    @patch("app.web.services.dashboard_service.read_db_task")
    @pytest.mark.asyncio
    async def test_no_task_found_raises_error(self, mock_read):
        """Should raise error when no active task found."""
        mock_read.return_value = None

        with pytest.raises(PlanReviewError, match="No active task found") as exc_info:
            await process_plan_review("approved", None)
        
        assert exc_info.value.status_code == 404

    @patch("app.web.services.dashboard_service.move_task_to_in_progress")
    @patch("app.web.services.dashboard_service.update_db_task")
    @patch("app.web.services.dashboard_service.read_db_task")
    @pytest.mark.asyncio
    async def test_rejection_in_wrong_state_raises_error(self, mock_read, mock_update, mock_move):
        """Should raise error when trying to reject in wrong state."""
        # Setup
        mock_task = AgentTask(task_id="test-123", plan_state="approved")
        mock_read.return_value = mock_task

        # Execute & Verify
        with pytest.raises(PlanReviewError, match="Plan can only be rejected when it is in review") as exc_info:
            await process_plan_review("rejected", "Test reason")
        
        assert exc_info.value.status_code == 409

    @patch("app.web.services.dashboard_service.update_db_task")
    @patch("app.web.services.dashboard_service.read_db_task")
    @pytest.mark.asyncio
    async def test_update_task_failure_raises_error(self, mock_read, mock_update):
        """Should raise error when task update fails."""
        # Setup
        mock_task = AgentTask(task_id="test-123", plan_state="created")
        mock_read.return_value = mock_task
        mock_update.return_value = None

        # Execute & Verify
        with pytest.raises(PlanReviewError, match="Failed to update task") as exc_info:
            await process_plan_review("approved", None)
        
        assert exc_info.value.status_code == 500

    @patch("app.web.services.dashboard_service._rollback_task_state")
    @patch("app.web.services.dashboard_service.move_task_to_in_progress")
    @patch("app.web.services.dashboard_service.add_plan_rejection_comment")
    @patch("app.web.services.dashboard_service.update_db_task")
    @patch("app.web.services.dashboard_service.read_db_task")
    @pytest.mark.asyncio
    async def test_comment_failure_triggers_rollback(self, mock_read, mock_update, mock_comment, mock_move, mock_rollback):
        """Should rollback state when comment addition fails."""
        # Setup
        mock_task = AgentTask(task_id="test-123", plan_state="created")
        mock_read.return_value = mock_task
        mock_updated = AgentTask(task_id="test-123", plan_state="rejected")
        mock_update.return_value = mock_updated
        mock_comment.side_effect = Exception("Comment failed")
        mock_rollback.return_value = True

        # Execute & Verify
        with pytest.raises(PlanReviewError, match="Failed to add rejection comment.*rolled back") as exc_info:
            await process_plan_review("rejected", "Test reason")
        
        assert exc_info.value.status_code == 500
        mock_rollback.assert_called_once_with("test-123", "created")

    @patch("app.web.services.dashboard_service._rollback_task_state")
    @patch("app.web.services.dashboard_service.move_task_to_in_progress")
    @patch("app.web.services.dashboard_service.update_db_task")
    @patch("app.web.services.dashboard_service.read_db_task")
    @pytest.mark.asyncio
    async def test_move_task_failure_triggers_rollback(self, mock_read, mock_update, mock_move, mock_rollback):
        """Should rollback state when moving task fails."""
        # Setup
        mock_task = AgentTask(task_id="test-123", plan_state="created")
        mock_read.return_value = mock_task
        mock_updated = AgentTask(task_id="test-123", plan_state="approved")
        mock_update.return_value = mock_updated
        mock_move.side_effect = Exception("Move failed")
        mock_rollback.return_value = True

        # Execute & Verify
        with pytest.raises(PlanReviewError, match="Failed to move task to in progress.*rolled back") as exc_info:
            await process_plan_review("approved", None)
        
        assert exc_info.value.status_code == 500
        mock_rollback.assert_called_once_with("test-123", "created")

    @patch("app.web.services.dashboard_service._rollback_task_state")
    @patch("app.web.services.dashboard_service.move_task_to_in_progress")
    @patch("app.web.services.dashboard_service.update_db_task")
    @patch("app.web.services.dashboard_service.read_db_task")
    @pytest.mark.asyncio
    async def test_move_task_returns_false_triggers_error(self, mock_read, mock_update, mock_move, mock_rollback):
        """Should raise error when move_task_to_in_progress returns False."""
        # Setup
        mock_task = AgentTask(task_id="test-123", plan_state="created")
        mock_read.return_value = mock_task
        mock_updated = AgentTask(task_id="test-123", plan_state="approved")
        mock_update.return_value = mock_updated
        mock_move.return_value = False

        # Execute & Verify
        with pytest.raises(PlanReviewError, match="Failed to move task to in progress") as exc_info:
            await process_plan_review("approved", None)
        
        assert exc_info.value.status_code == 500
        mock_rollback.assert_not_called()

    @patch("app.web.services.dashboard_service._rollback_task_state")
    @patch("app.web.services.dashboard_service.move_task_to_in_progress")
    @patch("app.web.services.dashboard_service.update_db_task")
    @patch("app.web.services.dashboard_service.read_db_task")
    @pytest.mark.asyncio
    async def test_unexpected_error_triggers_rollback(self, mock_read, mock_update, mock_move, mock_rollback):
        """Should rollback on unexpected errors."""
        # Setup
        mock_task = AgentTask(task_id="test-123", plan_state="created")
        mock_read.return_value = mock_task
        mock_update.side_effect = RuntimeError("Unexpected error")
        mock_rollback.return_value = True

        # Execute & Verify
        with pytest.raises(PlanReviewError, match="An unexpected error occurred.*rolled back") as exc_info:
            await process_plan_review("approved", None)
        
        assert exc_info.value.status_code == 500
        mock_rollback.assert_called_once_with("test-123", "created")


class TestPlanReviewError:
    """Tests for PlanReviewError exception."""

    def test_default_status_code(self):
        """Should use default status code 400."""
        error = PlanReviewError("Test message")
        assert error.status_code == 400
        assert str(error) == "Test message"

    def test_custom_status_code(self):
        """Should use custom status code when provided."""
        error = PlanReviewError("Test message", status_code=404)
        assert error.status_code == 404
        assert str(error) == "Test message"
