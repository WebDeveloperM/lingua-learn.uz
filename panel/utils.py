def save_ordered(formset, order_field='order', start=0, **parent):
    """Save an inline formset, numbering the surviving rows start, start+1... in the order they were submitted."""
    position = start
    for form in formset.forms:
        if form in formset.deleted_forms:
            if form.instance.pk:
                form.instance.delete()
            continue
        if not form.instance.pk and not form.has_changed():
            continue
        obj = form.save(commit=False)
        for field, value in parent.items():
            setattr(obj, field, value)
        setattr(obj, order_field, position)
        obj.save()
        position += 1
