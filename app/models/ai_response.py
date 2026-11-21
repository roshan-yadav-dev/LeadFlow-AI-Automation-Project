
from pydantic import BaseModel, Field


class AIEmailResponse(BaseModel):

    subject: str = Field(
        description="Professional and personalized email subject"
    )

    body: str = Field(
        description="Complete personalized email body"
    )

    lead_summary: str = Field(
        description="Short summary of the customer's requirements"
    )

    suggested_next_step: str = Field(
        description="A relevant next action for the business team"
    )
