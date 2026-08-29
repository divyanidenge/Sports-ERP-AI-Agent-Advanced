"""
app/agents/governance_agent.py
-------------------------------
User Governance & Administration Specialist Agent.
Responsible for user directory queries, administrative blocking/unblocking, and RBAC governance.
"""

from typing import Dict, Any
from app.agents.base_agent import BaseSportsAgent, AgentExecutionResult
import app.agent_tools as tools

class UserGovernanceAgent(BaseSportsAgent):
    def __init__(self):
        super().__init__(
            name="UserGovernanceAgent",
            role_title="Sports Administrator & Governance Officer",
            description="Manages user directories, role permissions, administrative block/unblock actions, and security governance.",
            tool_names=["get_all_users", "block_user", "unblock_user"]
        )

    def execute(self, subtask_name: str, params: Dict[str, Any], current_user: Dict[str, Any]) -> AgentExecutionResult:
        user_id = current_user.get("id", 0)
        user_role = current_user.get("role", "student")

        if subtask_name == "get_all_users":
            if user_role != "admin":
                return AgentExecutionResult(
                    agent_name=self.name,
                    success=False,
                    message="You don't have permission to perform this action. Only administrators can view the user directory."
                )
            res = tools.list_all_users_tool(role=user_role)
            return AgentExecutionResult(
                agent_name=self.name,
                success=res.get("success", True),
                message=res.get("message", ""),
                data=res.get("data", [])
            )

        elif subtask_name == "block_user":
            target_user_id = params.get("target_user_id", 0)
            res = tools.block_user_tool(role=user_role, user_identifier=str(target_user_id))
            return AgentExecutionResult(
                agent_name=self.name,
                success=res.get("success", False),
                message=res.get("message", ""),
                action_taken="block_user" if res.get("success") else None
            )

        elif subtask_name == "unblock_user":
            target_user_id = params.get("target_user_id", 0)
            res = tools.unblock_user_tool(role=user_role, user_identifier=str(target_user_id))
            return AgentExecutionResult(
                agent_name=self.name,
                success=res.get("success", False),
                message=res.get("message", ""),
                action_taken="unblock_user" if res.get("success") else None
            )

        return AgentExecutionResult(
            agent_name=self.name,
            success=False,
            message=f"Unknown subtask '{subtask_name}' for UserGovernanceAgent."
        )
