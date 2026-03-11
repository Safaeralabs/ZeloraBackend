class OrgScopedMixin:
    """Automatically scope querysets to the current user's organization."""

    def get_queryset(self):
        qs = super().get_queryset()
        return qs.filter(organization=self.request.user.organization)

    def perform_create(self, serializer):
        serializer.save(organization=self.request.user.organization)
