
from app.models.lead import LeadCreate

from app.services.groq_service import (
    generate_personalized_email
)


def main():

    lead = LeadCreate(
        name="Priya Patel",
        email="priya.demo@example.com",
        phone="9876543210",
        company="Digital Solutions",
        service="Website Development",
        requirements=(
            "I need a responsive business website "
            "with an admin dashboard and customer "
            "enquiry management."
        ),
        budget="25000-50000",
        preferred_contact="email",
        consent=True
    )

    result = generate_personalized_email(lead)

    print("\n========== GROQ AI OUTPUT ==========")

    print("\nSUBJECT:")
    print(result.subject)

    print("\nEMAIL BODY:")
    print(result.body)

    print("\nLEAD SUMMARY:")
    print(result.lead_summary)

    print("\nSUGGESTED NEXT STEP:")
    print(result.suggested_next_step)

    print("\n========== TEST SUCCESS ==========")


if __name__ == "__main__":
    main()
