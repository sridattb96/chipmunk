"""Seed the store with dummy recordings for user_id=1.

Run after backend is set up. The first user to sign in will get user_id=1
and see these recordings.
"""

import sys
from pathlib import Path

# Add backend to path
sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from app.db import add_recording

DUMMY_RECORDINGS = [
    {
        "name": "Call with Steve",
        "duration": "5:36",
        "summary": "The meeting focused on aligning cross-functional teams around the Q1 product launch timeline, scope, and key risks. The Product team began by reviewing the current roadmap and confirming that the core feature set remains unchanged. Two secondary features previously considered 'must-have' were officially moved to Phase 2 to reduce launch risk and protect timeline commitments.",
        "topics": ["Q1 product launch", "Phase 2"],
        "tone": "Professional, collaborative",
        "transcript": "Steve: Hey, thanks for jumping on. I wanted to sync on the Q1 launch...\n\n[Full transcript would go here. This is placeholder text for the dummy recording.]",
    },
    {
        "name": "Call with Matt about Landscaping",
        "duration": "12:24",
        "summary": "Discussion of backyard landscaping project. Matt provided three quotes for the patio extension and tree removal. We agreed to move forward with option B, which includes native plants and a stone path. Timeline is 4-6 weeks starting in March.",
        "topics": ["Landscaping", "Home improvement", "Patio"],
        "tone": "Casual, friendly",
        "transcript": "Matt: So I've got the numbers for you. Option A is the most basic...\n\n[Placeholder transcript.]",
    },
    {
        "name": "Weekly sync with Engineering",
        "duration": "22:10",
        "summary": "Engineering standup covering sprint 12 progress. Blockers: API rate limiting on the staging environment. DevOps to investigate. QA reported 3 critical bugs in the checkout flow. Aiming to ship hotfix by Friday.",
        "topics": ["Sprint planning", "Engineering", "QA"],
        "tone": "Technical, efficient",
        "transcript": "Dev lead: Let's go around. Backend, what's your status?...\n\n[Placeholder transcript.]",
    },
    {
        "name": "Interview debrief - Senior Designer",
        "duration": "18:45",
        "summary": "Post-interview discussion for the Senior Designer role. Strong portfolio, good systems thinking. Concern about limited mobile experience. Recommendation: move to final round. Compare with two other candidates before deciding.",
        "topics": ["Hiring", "Design", "Interview"],
        "tone": "Professional, evaluative",
        "transcript": "HR: So what did you think of the presentation?...\n\n[Placeholder transcript.]",
    },
]

USER_ID = 1


def main():
    # Add in reverse order so "Call with Steve" is most recent (appears first)
    for rec in reversed(DUMMY_RECORDINGS):
        add_recording(
            user_id=USER_ID,
            name=rec["name"],
            duration=rec["duration"],
            summary=rec["summary"],
            topics=rec["topics"],
            tone=rec["tone"],
            transcript=rec["transcript"],
        )
    print(f"Seeded {len(DUMMY_RECORDINGS)} recordings for user_id={USER_ID}")


if __name__ == "__main__":
    main()
