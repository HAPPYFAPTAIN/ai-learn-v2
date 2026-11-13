from html import escape


class WaitingMessage(str):
    pass


def waiting_panel(request_id, stage, title, detail, steps=()):
    milestones = ''.join(
        f'<li{" aria-current=step" if index == stage else ""}>{escape(label)}</li>'
        for index, label in enumerate(steps, 1)
    )
    return (
        f'<section class="le-ui-wait" role="status" aria-live="polite" '
        f'data-le-wait-id="{escape(str(request_id), quote=True)}" data-le-stage="{stage}">'
        f'<h3>{escape(title)}</h3>'
        + (f'<ol aria-label="生成阶段">{milestones}</ol>' if steps else '')
        + f'<p>{escape(detail)}</p><progress aria-label="正在等待模型响应"></progress>'
        '<span data-le-elapsed aria-live="off">正在等待模型响应…</span></section>'
    )
