from django.conf import settings
from django.contrib import messages
from django.contrib.auth.decorators import login_required
from django.contrib.admin.views.decorators import staff_member_required
from django.core.exceptions import PermissionDenied
from django.core.exceptions import SuspiciousOperation
from django.http import HttpResponse
from django.template.loader import render_to_string
from django.shortcuts import render
from django.shortcuts import get_object_or_404
from django.shortcuts import redirect
from django.utils.translation import ugettext as _
from django.views.decorators.csrf import csrf_protect
from pod.video.models import Video
from pod.video.views import is_in_video_groups
from pod.video.forms import VideoPasswordForm
from pod.enrichment.models import Enrichment
from pod.enrichment.forms import EnrichmentForm
from pod.enrichment.utils import enrichment_to_vtt

import json

ACTION = ['new', 'save', 'modify', 'delete', 'cancel']


@csrf_protect
@login_required
@staff_member_required
def video_enrichment(request, slug):
    video = get_object_or_404(Video, slug=slug)
    if request.user != video.owner and not request.user.is_superuser:
        messages.add_message(
            request, messages.ERROR, _(u'You cannot enrich this video.'))
        raise PermissionDenied

    list_enrichment = video.enrichment_set.all()
    if request.POST and request.POST.get('action'):
        if request.POST['action'] in ACTION:
            return eval(
                'video_enrichment_{0}(request, video)'.format(
                    request.POST['action'])
            )
    else:
        return render(
            request,
            'video_enrichment.html',
            {'video': video,
             'list_enrichment': list_enrichment})


def video_enrichment_new(request, video):
    list_enrichment = video.enrichment_set.all()

    form_enrichment = EnrichmentForm(
        initial={'video': video, 'start': 0, 'end': 1})
    if request.is_ajax():
        return render(
            request,
            'enrichment/form_enrichment.html',
            {'video': video,
             'form_enrichment': form_enrichment})
    else:
        return render(
            request,
            'video_enrichment.html',
            {'video': video,
             'list_enrichment': list_enrichment,
             'form_enrichment': form_enrichment})


def video_enrichment_save(request, video):
    list_enrichment = video.enrichment_set.all()

    form_enrichment = None
    if request.POST.get('enrich_id') != 'None':
        enrich = get_object_or_404(
            Enrichment, id=request.POST['enrich_id'])
        form_enrichment = EnrichmentForm(request.POST, instance=enrich)
    else:
        form_enrichment = EnrichmentForm(request.POST)

    if form_enrichment.is_valid():
        form_enrichment.save()
        list_enrichment = video.enrichment_set.all()
        enrichment_to_vtt(list_enrichment, video)
        if request.is_ajax():
            some_data_to_dump = {
                'list_enrichment': render_to_string(
                    'enrichment/list_enrichment.html',
                    {'list_enrichment': list_enrichment,
                     'video': video}),
            }
            data = json.dumps(some_data_to_dump)
            return HttpResponse(data, content_type='application/json')
        else:
            return render(
                request,
                'video_enrichment.html',
                {'video': video,
                 'list_enrichment': list_enrichment})
    else:
        if request.is_ajax():
            some_data_to_dump = {
                'errors': '{0}'.format(_('Please correct errors.')),
                'form': render_to_string(
                    'enrichment/form_enrichment.html', {
                        'video': video,
                        'form_enrichment': form_enrichment})
            }
            data = json.dumps(some_data_to_dump)
            return HttpResponse(data, content_type='application/json')
        else:
            return render(
                request,
                'video_enrichment.html',
                {'video': video,
                 'list_enrichment': list_enrichment,
                 'form_enrichment': form_enrichment})


def video_enrichment_modify(request, video):
    list_enrichment = video.enrichment_set.all()

    enrich = get_object_or_404(Enrichment, id=request.POST['id'])
    form_enrichment = EnrichmentForm(instance=enrich)
    if request.is_ajax():
        return render(
            request,
            'enrichment/form_enrichment.html',
            {'video': video,
             'form_enrichment': form_enrichment})
    else:
        return render(
            request,
            'video_enrichment.html',
            {'video': video,
             'list_enrichment': list_enrichment,
             'form_enrichment': form_enrichment})


def video_enrichment_delete(request, video):
    enrich = get_object_or_404(Enrichment, id=request.POST['id'])
    enrich.delete()
    list_enrichment = video.enrichment_set.all()
    if list_enrichment:
        enrichment_to_vtt(list_enrichment, video)
    if request.is_ajax():
        some_data_to_dump = {
            'list_enrichment': render_to_string(
                'enrichment/list_enrichment.html', {
                    'list_enrichment': list_enrichment,
                    'video': video
                })
        }
        data = json.dumps(some_data_to_dump)
        return HttpResponse(data, content_type='application/json')
    else:
        return render(
            request,
            'video_enrichment.html',
            {'video': video,
             'list_enrichment': list_enrichment})


def video_enrichment_cancel(request, video):
    list_enrichment = video.enrichment_set.all()
    return render(
        request,
        'video_enrichment.html',
        {'video': video,
         'list_enrichment': list_enrichment})


@csrf_protect
def video_enriched(request, slug, slug_private=None):
    try:
        id = int(slug[:slug.find("-")])
    except ValueError:
        raise SuspiciousOperation('Invalid video id')
    video = get_object_or_404(Video, id=id)

    is_draft = video.is_draft
    is_restricted = video.is_restricted
    is_restricted_to_group = video.restrict_access_to_groups.all().exists()
    is_password_protected = (video.password is not None)

    is_access_protected = (
        is_draft
        or is_restricted
        or is_restricted_to_group
        or is_password_protected
    )

    if is_access_protected:
        access_granted_for_private = (
            slug_private and slug_private == video.get_hashkey()
        )
        access_granted_for_draft = request.user.is_authenticated() and (
            request.user == video.owner or request.user.is_superuser)
        access_granted_for_restricted = (
            request.user.is_authenticated() and not is_restricted_to_group)
        access_granted_for_group = (
            request.user.is_authenticated()
            and is_in_video_groups(request.user, video)
        )

        show_page = (
            access_granted_for_private
            or
            (is_draft and access_granted_for_draft)
            or (
                is_restricted
                and access_granted_for_restricted
                and is_password_protected is False)
            or (
                is_restricted_to_group
                and access_granted_for_group
                and is_password_protected is False)
            or (
                is_password_protected
                and access_granted_for_draft
            )
            or (
                is_password_protected
                and request.POST.get('password')
                and request.POST.get('password') == video.password
            )
        )
        if show_page:
            return render(
                request, 'video_enriched.html', {
                    'video': video,
                }
            )
        else:
            if is_password_protected:
                form = VideoPasswordForm(
                    request.POST) if request.POST else VideoPasswordForm()
                return render(
                    request, 'video_enriched.html', {
                        'video': video,
                        'form': form
                    }
                )
            elif request.user.is_authenticated():
                messages.add_message(
                    request, messages.ERROR,
                    _(u'You cannot watch this video.'))
                raise PermissionDenied
            else:
                return redirect(
                    '%s?referrer=%s' % (settings.LOGIN_URL, request.path)
                )
    else:
        return render(
            request, 'video_enriched.html', {
                'video': video,
            }
        )