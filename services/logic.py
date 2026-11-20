def process_calculations(items: list) -> dict:
    """
    TUTAJ: Główna logika obliczeniowa / analityczna (dla Osoby 3).
    Dostosujcie to do tematu hackathonu (np. ryzyko, optymalizacja, sumy, scoring).
    """
    total_val = sum(i.value for i in items if i.value)
    count = len(items)
    avg_val = round(total_val / count, 2) if count > 0 else 0.0

    return {
        "count": count,
        "total_value": round(total_val, 2),
        "average_value": avg_val,
        "status": "Optimal" if total_val > 0 else "Pending"
    }
