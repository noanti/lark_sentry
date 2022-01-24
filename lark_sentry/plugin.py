# -*- coding: utf-8 -*-
import json
import logging
from collections import defaultdict

from django import forms
from django.utils.translation import ugettext_lazy as _

from sentry.plugins.bases import notify
from sentry.http import safe_urlopen
from sentry.utils.safe import safe_execute

from . import __version__, __doc__ as package_doc


class LarkNotificationsOptionsForm(notify.NotificationConfigurationForm):
    webhook = forms.CharField(
        label=_('Webhook'),
        widget=forms.TextInput(attrs={'placeholder': 'https://open.feishu.cn/open-apis/bot/hook/xxx'}),
        help_text=_('Read more: https://getfeishu.cn/hc/en-us/articles/360024984973-Use-Bots-in-group-chat'),
    )
    message_template = forms.CharField(
        label=_('Message template'),
        widget=forms.Textarea(attrs={'class': 'span4'}),
        help_text=_('Set in standard python\'s {}-format convention, available names are: '
                    '{project_name}, {url}, {title}, {message}, {tag[%your_tag%]}'),
        initial="{header} **Project**:&nbsp;&nbsp;{project_name}  **User**:&nbsp;&nbsp;{user}"
                "  **Env**:&nbsp;&nbsp;{environment} **Ver**:&nbsp;&nbsp;{release}"
                " **Msg**:&nbsp;&nbsp;{message} <btn:click>{url}"
    )


class LarkSentryNotificationsPlugin(notify.NotificationPlugin):
    title = 'Lark Sentry Notifications'
    slug = 'lark_sentry'
    description = package_doc
    version = __version__
    author = 'x0216u'
    author_url = 'https://github.com/x0216u/lark_sentry'
    resource_links = [
        ('Bug Tracker', 'https://github.com/x0216u/lark_sentry/issues'),
        ('Source', 'https://github.com/x0216u/lark_sentry/issues'),
    ]

    conf_key = 'lark_sentry'
    conf_title = title

    project_conf_form = LarkNotificationsOptionsForm

    logger = logging.getLogger('sentry.plugins.lark_sentry')

    def is_configured(self, project, **kwargs):
        return bool(self.get_option('webhook_url', project) and self.get_option('message_template', project))

    def get_config(self, project, **kwargs):
        default_template = """{title}
{transaction}
{request[method] request[url]}
{location}
{metadata[filename]}:{metadata[function]}
"""
        return [
            {
                'name': 'webhook_url',
                'label': 'webhook_url',
                'type': 'text',
                'help': 'Read more: https://getfeishu.cn/hc/en-us/articles/360024984973-Use-Bots-in-group-chat',
                'placeholder': 'https://open.feishu.cn/open-apis/bot/v2/hook/xxxx',
                'validators': [],
                'required': True,
            },
            {
                'name': 'message_template',
                'label': 'Message Template',
                'type': 'textarea',
                'help': 'Set in standard python\'s {}-format convention, available names are: '
                        'Undefined tags will be shown as [not set], [hr] means underline, [btn:text] means a button,'
                        ' [br] means next line',
                'validators': [],
                'required': True,
                'default': default_template,
            },
        ]

    def build_message(self, group, event):
        template = str(self.get_message_template(group.project))
        msg = template.format(**event)
        lines = msg.split('\n')

        body = {
            "msg_type": "interactive",
            "card": {
                "config": {
                    "wide_screen_mode": True
                }
            }
        }
        elements = []
        if lines:
            body['card']['header'] = {"title": {"tag": "plain_text",
                                                "content": str(full_text_list.pop(0)).format(**names)}}
            for line in lines:
                line = str(line)
                if not line.strip():
                    continue
                if line == '<hr>':
                    elements.append({
                        "tag": "hr"
                    })
                elif line.startswith('<btn:'):
                    btn_arr = line.split('>')
                    url = btn_arr[-1]
                    btn_text = btn_arr[0].split(':')[-1]
                    elements.append({
                        "tag": "action",
                        "actions": [
                            {
                                "tag": "button",
                                "url": url,
                                "text": {
                                    "tag": "plain_text",
                                    "content": str(btn_text)
                                },
                                "type": "primary"
                            }
                        ]
                    })
                else:
                    elements.append({
                        "tag": "div",
                        "text": {
                            "tag": "lark_md",
                            "content": str(line)
                        }
                    })
        body['card']['elements'] = elements

        return body

    def get_message_template(self, project):
        return self.get_option('message_template', project)

    def send_message(self, url, payload):
        self.logger.debug('Sending message to %s ' % url)
        response = safe_urlopen(
            method='POST',
            url=url,
            json=payload,
        )
        self.logger.debug('Response code: %s, content: %s' % (response.status_code, response.content))

    def notify_users(self, group, event, fail_silently=False, **kwargs):
        self.logger.debug('Received notification for event tag: %s' % event.tags)
        payload = self.build_message(group, event)
        self.logger.debug('Built payload: %s' % payload)
        url = self.get_option('webhook', group.project)
        self.logger.debug('Webhook url: %s' % url)
        safe_execute(self.send_message, url, payload, _with_transaction=False)
