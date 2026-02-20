from server.app.prompts import JOB_ANALYSIS_PROMPT_TEMPLATE


def test_job_analysis_prompt_template_has_required_placeholders() -> None:
    required = ("{user_specs}", "{company}", "{title}", "{content}", "{format_instructions}")
    for placeholder in required:
        assert placeholder in JOB_ANALYSIS_PROMPT_TEMPLATE
