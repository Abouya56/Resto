from django.contrib.auth import authenticate
from rest_framework import generics, permissions, status, viewsets
from rest_framework.response import Response
from rest_framework.throttling import ScopedRateThrottle
from rest_framework_simplejwt.tokens import RefreshToken

from apps.core.permissions import IsPlatformAdmin
from apps.core.security import client_ip
from apps.users import lockout
from apps.users.models import User
from apps.users.serializers import (
    ChangePasswordSerializer,
    UserSerializer,
)


class LoginAPIView(generics.GenericAPIView):
    permission_classes = [permissions.AllowAny]
    serializer_class = UserSerializer
    throttle_classes = [ScopedRateThrottle]
    throttle_scope = "login"

    def post(self, request):
        email = request.data.get("email")
        password = request.data.get("password")
        ip = client_ip(request)
        if lockout.is_locked(email, ip):
            return Response({"detail": lockout.LOCKED_MESSAGE}, status=status.HTTP_429_TOO_MANY_REQUESTS)
        user = authenticate(request, username=email, password=password)
        if not user:
            lockout.register_failure(email, ip)
            return Response({"detail": "Identifiants invalides."}, status=status.HTTP_400_BAD_REQUEST)
        lockout.reset(email)
        refresh = RefreshToken.for_user(user)
        return Response(
            {
                "access": str(refresh.access_token),
                "refresh": str(refresh),
                "user": UserSerializer(user).data,
            }
        )


class MeAPIView(generics.RetrieveUpdateAPIView):
    serializer_class = UserSerializer

    def get_object(self):
        return self.request.user


class ChangePasswordAPIView(generics.GenericAPIView):
    serializer_class = ChangePasswordSerializer

    def post(self, request):
        serializer = self.get_serializer(data=request.data)
        serializer.is_valid(raise_exception=True)
        if not request.user.check_password(serializer.validated_data["old_password"]):
            return Response({"detail": "Ancien mot de passe incorrect."}, status=400)
        request.user.set_password(serializer.validated_data["new_password"])
        request.user.save()
        return Response({"detail": "Mot de passe mis à jour."})


class AdminUserViewSet(viewsets.ReadOnlyModelViewSet):
    serializer_class = UserSerializer
    permission_classes = [IsPlatformAdmin]
    queryset = User.objects.all()
    search_fields = ("email", "first_name", "last_name")
    filterset_fields = ("role", "is_active")
