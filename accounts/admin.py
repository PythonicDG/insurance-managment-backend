from django.contrib import admin
from django.db import models
from . import models as app_models


for model in app_models.__dict__.values():
    if isinstance(model, type) and issubclass(model, models.Model):
        admin.site.register(model)
