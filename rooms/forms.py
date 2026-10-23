from django import forms


class JoinForm(forms.Form):
    display_name = forms.CharField(
        label="Your name",
        max_length=30,
        widget=forms.TextInput(attrs={"autofocus": True, "autocomplete": "nickname"}),
    )
