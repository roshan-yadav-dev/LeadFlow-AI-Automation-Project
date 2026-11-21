
from app.models.lead import LeadCreate
from app.services.gemini_service import (
    generate_personalized_email
)


def main():

    lead = LeadCreate(
        name="Rahul Sharma",
        email="rahul.demo@example.com",
        phone="9876543210",
        company="TechSolutions",
        service="AI Automation",
        requirements=(
            "I want to automate customer support "
            "and lead management."
        ),
        budget="10000-25000",
        preferred_contact="email",
        consent=True
    )

    result = generate_personalized_email(lead)

    print("\n--- GENERATED EMAIL ---")

    print("Subject:", result.subject)
    print("\nBody:\n", result.body)

    print("\nLead Summary:", result.lead_summary)

    print(
        "\nNext Step:",
        result.suggested_next_step
    )


if __name__ == "__main__":
    main()
