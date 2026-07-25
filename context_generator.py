import re
import random
from typing import Dict, Any, Optional, List


CONTEXT_TEMPLATES = {
    "sales_intro": {
        "subjects": [
            "Quick question about {company}",
            "Potential opportunity for {name} at {company}",
            "Helping {company} grow",
            "A thought for {company} - {name}",
        ],
        "body": """
<p>Hi {name},</p>
<p>I hope this email finds you well. I was doing some research on {company} and came across the impressive work you're doing in the industry.</p>
<p>We specialize in helping companies like {company} achieve {pain_point}. Based on what I've seen, I believe there could be a meaningful opportunity for us to collaborate.</p>
<p>Would you be open to a 15-minute call next week to explore this further? I'd love to share a few specific ideas that have helped similar businesses.</p>
<p>Looking forward to hearing from you.</p>
<p>Best regards,<br>{sender_name}</p>
""".strip(),
    },
    "follow_up": {
        "subjects": [
            "Following up: {company} opportunity",
            "Checking in, {name}",
            "Re: Our earlier thought for {company}",
        ],
        "body": """
<p>Hi {name},</p>
<p>I wanted to circle back on my earlier note regarding {company}. I know you're busy, so I wanted to make sure this didn't get lost in the shuffle.</p>
<p>To recap, we help companies in your space with {pain_point}. We've recently delivered measurable results for a few peers of {company}, and I'd be glad to walk you through a quick overview.</p>
<p>If you're available for a brief chat sometime this week or next, just let me know what works best for your schedule.</p>
<p>Talk soon,<br>{sender_name}</p>
""".strip(),
    },
    "product_update": {
        "subjects": [
            "New: {product} update for {company}",
            "Exciting news for {name} at {company}",
            "What's new that matters for {company}",
        ],
        "body": """
<p>Hi {name},</p>
<p>I'm reaching out because I noticed {company} has been focusing on {focus_area}, and I thought you'd want to know about our latest {product} updates.</p>
<p>Here are a few highlights that are directly relevant to teams like yours:</p>
<ul>
<li><strong>Feature A:</strong> {feature_a_benefit}</li>
<li><strong>Feature B:</strong> {feature_b_benefit}</li>
<li><strong>Feature C:</strong> {feature_c_benefit}</li>
</ul>
<p>Would you be interested in a quick walkthrough? I can tailor it specifically to how {company} operates.</p>
<p>Warmly,<br>{sender_name}</p>
""".strip(),
    },
    "partnership_proposal": {
        "subjects": [
            "Partnership idea: {company} x {our_company}",
            "Exploring synergy between {company} and {our_company}",
            "A mutual growth idea for {name}",
        ],
        "body": """
<p>Hi {name},</p>
<p>I've been following {company}'s journey for a while, and I'm genuinely impressed by the value you bring to your customers.</p>
<p>I work with {our_company}, and I've been thinking about how our two organizations could create something great together. Specifically:</p>
<ul>
<li>Our customers frequently ask about services/products that {company} offers</li>
<li>{company} clients could benefit from {our_value_prop}</li>
<li>We share a similar target audience and market philosophy</li>
</ul>
<p>Would you be open to a 20-minute exploratory conversation? There's no pressure — just a chance to see if there's real alignment.</p>
<p>Cheers,<br>{sender_name}</p>
""".strip(),
    },
    "retarget": {
        "subjects": [
            "Gentle nudge: {company}",
            "Still interested in helping {company}, {name}",
            "Reconnecting re: {company}",
        ],
        "body": """
<p>Hi {name},</p>
<p>I wanted to reach out one more time. Last week, I shared a few ideas on how we could help {company} with {pain_point}.</p>
<p>Given that we haven't connected yet, I totally understand if:</p>
<ul>
<li>This isn't a priority right now — I can circle back later</li>
<li>There's someone else on your team I should talk to instead</li>
<li>It's just not the right fit — I'd appreciate a quick "no thanks" so I can stop following up</li>
</ul>
<p>No hard feelings either way. Just let me know what makes sense.</p>
<p>Best,<br>{sender_name}</p>
""".strip(),
    },
}


class ContextGenerator:
    def __init__(self, sender_name: str, our_company: str = None,
                 custom_templates: Dict[str, Any] = None):
        self.sender_name = sender_name
        self.our_company = our_company or "Our Company"
        self.templates = dict(CONTEXT_TEMPLATES)
        if custom_templates:
            self.templates.update(custom_templates)

    def list_context_tags(self) -> List[str]:
        return list(self.templates.keys())

    @staticmethod
    def _fill(template: str, data: Dict[str, Any]) -> str:
        result = template
        for key, value in data.items():
            if value is None:
                value = ""
            result = result.replace("{" + key + "}", str(value))
        result = re.sub(r"\{[a-zA-Z_]+\}", "", result)
        return result

    def generate(self, to_email: str, to_name: str,
                 context_tag: str = "sales_intro",
                 company: str = None,
                 extra_vars: Dict[str, Any] = None,
                 is_retarget: bool = False) -> Dict[str, str]:
        tag = context_tag if (not is_retarget and context_tag in self.templates) else "retarget"
        if is_retarget:
            tag = "retarget"
        if tag not in self.templates:
            tag = "sales_intro"

        template = self.templates[tag]
        subjects = template["subjects"]
        subject_template = random.choice(subjects)

        data = {
            "name": to_name or to_email.split("@")[0],
            "email": to_email,
            "company": company or "your company",
            "sender_name": self.sender_name,
            "our_company": self.our_company,
            "pain_point": "scaling their operations and reducing costs",
            "focus_area": "digital transformation",
            "product": "platform",
            "feature_a_benefit": "Save up to 40% on operational overhead",
            "feature_b_benefit": "Automate repetitive tasks end-to-end",
            "feature_c_benefit": "Real-time analytics that drive decisions",
            "our_value_prop": "our integrated platform and existing client network",
        }
        if extra_vars:
            data.update(extra_vars)

        subject = self._fill(subject_template, data)
        body_html = self._fill(template["body"], data)
        body_text = re.sub(r"<[^>]+>", "", body_html)

        return {
            "context_tag": tag,
            "subject": subject,
            "body_html": body_html,
            "body_text": body_text,
        }

    def generate_batch(self, recipients: List[Dict[str, Any]]) -> List[Dict[str, Any]]:
        rendered = []
        for rec in recipients:
            gen = self.generate(
                to_email=rec["to_email"],
                to_name=rec.get("to_name"),
                context_tag=rec.get("context_tag", "sales_intro"),
                company=rec.get("company"),
                extra_vars=rec.get("extra_vars"),
                is_retarget=rec.get("is_retarget", False),
            )
            rendered.append({**rec, **gen})
        return rendered
