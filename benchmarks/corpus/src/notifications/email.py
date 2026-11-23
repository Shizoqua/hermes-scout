"""Weekly digest emails."""


def build_digest(user, tasks, base_url):
    lines = [f"Hi {user['name']}, here is your week:"]
    lines += [f"- {task['title']}" for task in tasks]
    lines.append(f"Turn these off any time: {base_url}/settings/notifications?off=digest")
    return "\n".join(lines)


def send_digest(smtp, user, body):
    if not user.get("digest_opt_in", True):
        return False
    smtp.send(to=user["email"], subject="Your week in Larkspur", body=body)
    return True
