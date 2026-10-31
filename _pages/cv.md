---
layout: archive
title: "CV"
permalink: /cv/
author_profile: true
redirect_from:
  - /resume
---
<p>
See also:
<a href="https://researchmap.jp/fumiyaokazaki"
   target="_blank"
   rel="noopener noreferrer">researchmap</a>.
</p>

{% assign cvdata = site.data.researchmap_cv %}

{% if cvdata %}

{% for section in cvdata.sections %}

<h2>{{ section.title | escape }}</h2>

{% if section.items.size > 0 %}

<ul>
{% for item in section.items %}
<li style="margin-bottom: 1.2em;">

{% if item.period != "" %}
<strong>{{ item.period | escape }}</strong><br>
{% endif %}

{{ item.text | escape }}

{% if item.grant_number != "" %}
<br>Grant No.: {{ item.grant_number | escape }}
{% endif %}

{% if item.missing_english.size > 0 %}
<br>
<small>
Some details have no English entry on researchmap.
</small>
{% endif %}

</li>
{% endfor %}
</ul>

{% else %}

<p>No public entries are available.</p>

{% endif %}

{% endfor %}

{% else %}

<p>CV data has not been synchronized yet.</p>

{% endif %}
