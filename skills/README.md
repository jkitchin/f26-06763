# Agent skills for 06-763

`course-06763` is a study companion for the course that works in Claude Code, Codex,
OpenCode, Gemini CLI, Cursor and other agents that read the
[Agent Skills](https://agentskills.io/specification) format. It answers from the published
notes with links, coaches graded work within the syllabus's generative-AI policy, and only
uses material that has been released on the course site.

Install it into the project you use for the course (requires [uv](https://docs.astral.sh/uv/)):

```bash
uvx --from git+https://github.com/jkitchin/knowhow knowhow add jkitchin/f26-06763 --skill course-06763
```

or for every project on your machine, add `-g`. `npx skills add jkitchin/f26-06763 --skill
course-06763` also works. Update it later with `knowhow upgrade`.

The skill is copied to `.agents/skills/course-06763/` (read by Codex and most other agents)
and linked into `.claude/skills/` for Claude Code. In Claude Code it loads when you mention
the course, a lecture or an assignment; you can also call it with `/course-06763`. In Codex,
mention the course or name the skill.
