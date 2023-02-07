from aiohttp.web import HTTPForbidden, HTTPUnauthorized
from aiohttp_apispec import request_schema, response_schema
from aiohttp_session import new_session

from app.admin.schemes import AdminSchema
from app.web.app import View
from app.web.mixins import AuthRequiredMixin
from app.web.utils import json_response


class AdminLoginView(View):
    @request_schema(AdminSchema)
    @response_schema(AdminSchema, 200)
    async def post(self):
        admin = await self.request.app.store.admins.get_by_email(self.data["email"])
        password = self.data["password"]
        if admin is None or not admin.is_password_valid(password):
            raise HTTPForbidden

        admin_data = {"id": admin.id, "email": admin.email}
        session = await new_session(self.request)
        session["admin"] = admin_data
        return json_response(data=admin_data)


class AdminCurrentView(AuthRequiredMixin, View):
    @response_schema(AdminSchema, 200)
    async def get(self):
        admin = self.request.admin
        return json_response(data=AdminSchema().dump(admin))
    