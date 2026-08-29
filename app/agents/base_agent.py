"""
app/agents/base_agent.py
-------------------------
Base specification for role-aligned ERP agents in Sports ERP.
Inspired by Agentic ERP (Liu et al., 2026).
"""

from abc import ABC, abstractmethod
from typing import Dict, Any, List, Optional
from pydantic import BaseModel, Field

class AgentExecutionResult(BaseModel):
    agent_name: str
    success: bool
    message: str
    data: Optional[Any] = None
    pending_confirmation: bool = False
    suggested_slots: List[str] = Field(default_factory=list)
    action_taken: Optional[str] = None
    details: Dict[str, Any] = Field(default_factory=dict)

class BaseSportsAgent(ABC):
    """
    Abstract base class for a role-aligned Sports ERP specialist agent.
    Each agent exposes a role-scoped set of tools to minimize tool-selection complexity.
    """
    def __init__(self, name: str, role_title: str, description: str, tool_names: List[str]):
        self.name = name
        self.role_title = role_title
        self.description = description
        self.tool_names = tool_names

    @abstractmethod
    def execute(self, subtask_name: str, params: Dict[str, Any], current_user: Dict[str, Any]) -> AgentExecutionResult:
        """Executes a scoped tool/subtask on behalf of the authenticated user."""
        pass
