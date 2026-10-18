---
name: new-model
description: Add or change a Django model in a Sportie app (community_game_ranker or video_analyzer), including admin registration, migration, model test, and the data-model doc update. Use whenever creating or modifying database entities.
---

# New / changed Django model

Arguments: `<app_label> <ModelName>` plus a description of the fields, if given.

1. Read `.claude/docs/data-model.md`, and use the fields and relations it lists for this model. If
   the request conflicts with the doc, follow the request and update the doc afterward.
2. Edit `backend/apps/<app>/models.py`:
   - Use `TextChoices` for enum fields and `settings.AUTH_USER_MODEL` for user FKs.
   - Set `related_name` on every FK. Add `Meta.constraints` (`UniqueConstraint`) and `indexes`
     where the doc calls for them.
   - Write a `__str__` that returns something readable.
3. Register the model in `backend/apps/<app>/admin.py` (create the file if it's missing) with
   `list_display` set to the 3-5 most useful fields.
4. Run `cd backend && python manage.py makemigrations <app_label> --name <short_description>`.
   If Postgres isn't running, start it with `docker compose --profile dev up -d db`.
5. Add tests in `backend/apps/<app>/tests/test_models.py` covering constraints, `__str__`,
   and any custom methods. Run `pytest apps/<app> -q`.
6. Update the model's table in `.claude/docs/data-model.md`.

Don't create serializers or views here. Use `/new-endpoint` for those.
