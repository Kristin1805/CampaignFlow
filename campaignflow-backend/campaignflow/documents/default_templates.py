from campaignflow.documents.enums import DocumentTemplateCategory as Category


def field(identifier, label, field_type="text", required=False, **kwargs):
    return {
        "id": identifier,
        "label": label,
        "type": field_type,
        "required": required,
        "editable": True,
        **kwargs,
    }


def section(identifier, title, section_type="rich_text", required=False, **kwargs):
    return {
        "id": identifier,
        "title": title,
        "type": section_type,
        "required": required,
        **kwargs,
    }


def table(identifier, title, columns, **kwargs):
    return section(identifier, title, "table", columns=columns, **kwargs)


def structure(*sections):
    return {
        "schema_version": 1,
        "sections": list(sections),
    }


def template(code, name, category, description, sections):
    return {
        "code": code,
        "name": name,
        "category": category,
        "description": description,
        "draft_structure": sections,
    }


def campaign_information():
    return section(
        "campaign_information", "Campaign information", "key_value",
        fields=[
            field("campaign_name", "Campaign name", placeholder="campaign.name"),
            field("workspace_name", "Workspace", placeholder="workspace.name"),
            field("start_date", "Start date", "date", placeholder="campaign.start_date"),
            field("launch_date", "Launch date", "date", placeholder="campaign.launch_date"),
        ],
    )


def task_table():
    return table(
        "tasks", "Campaign tasks",
        [
            field("title", "Task"),
            field("assignee", "Assignee"),
            field("due_date", "Due date", "date"),
            field("status", "Status"),
        ],
        placeholder="campaign.tasks",
    )


DEFAULT_DOCUMENT_TEMPLATES = [
    # 1. Campaign Brief
    template(
        "campaign-brief", "Campaign Brief", Category.BRIEF,
        "Define campaign objectives, audience and deliverables.",
        structure(
            campaign_information(),
            section("overview", "Campaign overview", placeholder="campaign.description"),
            section("objectives", "Objectives", required=True, placeholder="campaign.objectives"),
            section("target_audience", "Target audience"),
            section("key_messages", "Key messages"),
            section("deliverables", "Expected deliverables"),
            section("success_metrics", "Success metrics"),
            task_table(),
        ),
    ),

    # 2. Creative Brief
    template(
        "creative-brief", "Creative Brief", Category.BRIEF,
        "Define creative direction and production requirements.",
        structure(
            campaign_information(),
            section("objective", "Creative objective", required=True),
            section("audience", "Target audience"),
            section("concept", "Creative concept"),
            section("visual_direction", "Visual direction"),
            section("tone", "Tone of voice"),
            section("references", "Creative references"),
            section(
                "requirements", "Production requirements", "checklist",
                items=[
                    "Brand guidelines reviewed",
                    "Visual direction approved",
                    "Required formats confirmed",
                    "Final assets reviewed",
                ],
            ),
        ),
    ),

    # 3. Marketing Strategy
    template(
        "marketing-strategy", "Marketing Strategy", Category.STRATEGY,
        "Define the overall marketing direction.",
        structure(
            campaign_information(),
            section("market_analysis", "Market analysis"),
            section("positioning", "Brand positioning"),
            section("objectives", "Strategic objectives"),
            section("audience", "Target audience"),
            section("channels", "Marketing channels"),
            section("tactics", "Marketing tactics"),
            section("budget", "Budget allocation"),
            table("kpis", "Success metrics", [
                field("metric", "Metric", required=True),
                field("baseline", "Baseline", "decimal"),
                field("target", "Target", "decimal"),
                field("actual", "Actual", "decimal"),
            ]),
        ),
    ),

    # 4. Social Media Strategy
    template(
        "social-media-strategy", "Social Media Strategy", Category.SOCIAL_MEDIA,
        "Plan social media communication and content.",
        structure(
            campaign_information(),
            section("goals", "Social media goals"),
            section("audience", "Audience"),
            section("content_pillars", "Content pillars"),
            section("tone", "Tone of voice"),
            table("platforms", "Platform strategy", [
                field("platform", "Platform", required=True),
                field("objective", "Objective"),
                field("frequency", "Posting frequency"),
                field("formats", "Content formats"),
                field("kpi", "Primary KPI"),
            ]),
            section("community", "Community management"),
            section("reporting", "Reporting approach"),
        ),
    ),

    # 5. Content Production Brief
    template(
        "content-production-brief", "Content Production Brief", Category.CONTENT,
        "Organize content production requirements.",
        structure(
            campaign_information(),
            section("objective", "Content objective"),
            section("concept", "Content concept"),
            section("requirements", "Production requirements"),
            table("deliverables", "Deliverables", [
                field("title", "Deliverable"),
                field("platform", "Platform"),
                field("format", "Format"),
                field("assignee", "Responsible person"),
                field("deadline", "Deadline", "date"),
            ]),
            section("approval", "Approval requirements"),
        ),
    ),

    # 6. Video Script
    template(
        "video-script", "Video Script", Category.CONTENT,
        "Prepare scene-by-scene video scripts.",
        structure(
            campaign_information(),
            section("video_objective", "Video objective"),
            section("hook", "Opening hook"),
            section("duration", "Target duration in seconds", "number"),
            table("scenes", "Scene breakdown", [
                field("scene", "Scene", "number", required=True),
                field("duration", "Duration in seconds", "number"),
                field("visual", "Visual direction", "long_text"),
                field("dialogue", "Dialogue", "long_text"),
                field("overlay", "On-screen text", "long_text"),
                field("audio", "Audio instructions"),
            ]),
            section("cta", "Call to action", "plain_text"),
            section("production_notes", "Production notes"),
        ),
    ),

    # 7. Copywriting Document
    template(
        "copywriting-document", "Copywriting Document", Category.CONTENT,
        "Prepare and organize marketing copy.",
        structure(
            campaign_information(),
            section("audience", "Target audience"),
            section("tone", "Tone of voice"),
            section("headline", "Headline", "plain_text"),
            section("main_copy", "Main copy", required=True),
            section("alternative_copy", "Alternative copy"),
            section("cta", "Call to action", "plain_text"),
            section("keywords", "Keywords"),
            section("notes", "Editorial notes"),
        ),
    ),

    # 8. Influencer Marketing Plan
    template(
        "influencer-marketing-plan", "Influencer Marketing Plan", Category.INFLUENCER,
        "Plan influencer collaborations and campaign objectives.",
        structure(
            campaign_information(),
            section("objectives", "Objectives"),
            section("criteria", "Influencer selection criteria"),
            section("deliverables", "Collaboration deliverables"),
            table("collaborations", "Planned collaborations", [
                field("influencer", "Influencer"),
                field("platform", "Platform"),
                field("deliverable", "Deliverable"),
                field("budget", "Budget", "currency"),
                field("deadline", "Deadline", "date"),
            ]),
            section("measurement", "Performance measurement"),
        ),
    ),

    # 9. Influencer Database
    template(
        "influencer-database", "Influencer Database", Category.INFLUENCER,
        "Maintain a structured influencer database.",
        structure(
            table("influencers", "Influencers", [
                field("name", "Name", required=True),
                field("platform", "Platform"),
                field("profile", "Profile URL", "url"),
                field("followers", "Followers", "number"),
                field("engagement", "Engagement rate", "percentage"),
                field("contact", "Contact information"),
                field("price", "Price", "currency"),
                field("currency", "Currency", "choice", options=["EUR", "USD", "GBP"]),
                field("status", "Status", "choice", options=[
                    "New", "Contacted", "Negotiating", "Confirmed", "Rejected",
                ]),
                field("notes", "Notes", "long_text"),
            ]),
        ),
    ),

    # 10. Media Plan
    template(
        "media-plan", "Media Plan", Category.ADVERTISING,
        "Plan paid media activities and spending.",
        structure(
            campaign_information(),
            section("objectives", "Advertising objectives"),
            table("media_channels", "Media channels", [
                field("channel", "Channel"),
                field("placement", "Placement"),
                field("audience", "Audience"),
                field("budget", "Budget", "currency"),
                field("start_date", "Start date", "date"),
                field("end_date", "End date", "date"),
                field("impressions", "Target impressions", "number"),
                field("cpc", "Target CPC", "currency"),
            ]),
            section("optimization", "Optimization strategy"),
        ),
    ),

    # 11. Campaign Budget
    template(
        "campaign-budget", "Campaign Budget", Category.FINANCE,
        "Track planned and actual campaign expenses.",
        structure(
            campaign_information(),
            section("currency", "Currency", "select", options=["EUR", "USD", "GBP"]),
            table("expenses", "Budget breakdown", [
                field("category", "Category", required=True),
                field("description", "Description"),
                field("planned", "Planned amount", "currency"),
                field("actual", "Actual amount", "currency"),
                field("supplier", "Supplier"),
                field("paid", "Paid", "boolean", default=False),
                field("notes", "Notes"),
            ]),
        ),
    ),

    # 12. Competitor Analysis
    template(
        "competitor-analysis", "Competitor Analysis", Category.ANALYTICS,
        "Compare competitors and identify opportunities.",
        structure(
            section("market", "Market overview"),
            table("competitors", "Competitor comparison", [
                field("name", "Competitor", required=True),
                field("website", "Website", "url"),
                field("positioning", "Positioning"),
                field("strengths", "Strengths", "long_text"),
                field("weaknesses", "Weaknesses", "long_text"),
                field("channels", "Marketing channels"),
                field("notes", "Notes", "long_text"),
            ]),
            section("opportunities", "Identified opportunities"),
            section("recommendations", "Recommendations"),
        ),
    ),

    # 13. Client Feedback
    template(
        "client-feedback", "Client Feedback", Category.FEEDBACK,
        "Collect and organize client feedback.",
        structure(
            campaign_information(),
            section("general_feedback", "General feedback"),
            table("feedback_items", "Feedback items", [
                field("deliverable", "Deliverable"),
                field("feedback", "Feedback", "long_text"),
                field("priority", "Priority", "choice", options=["Low", "Medium", "High"]),
                field("assignee", "Responsible person"),
                field("deadline", "Deadline", "date"),
                field("resolved", "Resolved", "boolean", default=False),
            ]),
            section("next_steps", "Next steps"),
        ),
    ),

    # 14. Campaign Performance Report
    template(
        "campaign-performance-report", "Campaign Performance Report", Category.ANALYTICS,
        "Summarize campaign performance and results.",
        structure(
            campaign_information(),
            section("summary", "Executive summary"),
            table("metrics", "Performance metrics", [
                field("metric", "Metric"),
                field("target", "Target", "decimal"),
                field("actual", "Actual", "decimal"),
                field("notes", "Notes"),
            ]),
            section("achievements", "Key achievements"),
            section("challenges", "Challenges"),
            section("recommendations", "Recommendations"),
        ),
    ),

    # 15. PR Strategy
    template(
        "pr-strategy", "PR Strategy", Category.PR,
        "Plan public relations activities.",
        structure(
            campaign_information(),
            section("objectives", "PR objectives"),
            section("messages", "Key messages"),
            table("media_contacts", "Media contacts", [
                field("publication", "Publication"),
                field("contact", "Contact"),
                field("topic", "Pitch topic"),
                field("status", "Status"),
                field("publication_date", "Publication date", "date"),
            ]),
            section("timeline", "PR timeline"),
            section("crisis_plan", "Crisis communication plan"),
        ),
    ),

    # 16. Event Planning
    template(
        "event-planning", "Event Planning", Category.EVENTS,
        "Organize marketing events.",
        structure(
            section("event_name", "Event name", "plain_text", required=True),
            section("event_date", "Event date", "date"),
            section("location", "Location", "plain_text"),
            section("objectives", "Event objectives"),
            table("agenda", "Event agenda", [
                field("start_at", "Start time", "datetime"),
                field("activity", "Activity"),
                field("responsible", "Responsible person"),
                field("location", "Location"),
            ]),
            section("logistics", "Logistics"),
            section("promotion", "Event promotion"),
        ),
    ),

    # 17. Meeting Notes
    template(
        "meeting-notes", "Meeting Notes", Category.OPERATIONS,
        "Record meetings and action items.",
        structure(
            section("meeting_date", "Meeting date", "date"),
            section("participants", "Participants"),
            section("agenda", "Agenda"),
            section("discussion", "Discussion"),
            section("decisions", "Decisions"),
            table("action_items", "Action items", [
                field("action", "Action", required=True),
                field("assignee", "Responsible person"),
                field("deadline", "Deadline", "date"),
                field("completed", "Completed", "boolean", default=False),
            ]),
        ),
    ),

    # 18. Custom Document
    template(
        "custom-document", "Custom Document", Category.CUSTOM,
        "A flexible starting point for custom documents.",
        structure(
            section("content", "Document content"),
        ),
    ),
]

SYSTEM_TEMPLATE_CODES = frozenset(
    item["code"] for item in DEFAULT_DOCUMENT_TEMPLATES
)