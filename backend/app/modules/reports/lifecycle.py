"""Життєвий цикл статусів заявки (KAN-59, п. 2.2, БП-3, БП-6, табл. 13).

Допустимі переходи:

    «Нова» → «Прийнята» → «В роботі» → «Усунена»            (власні сили служби)
                          «В роботі» → «Виконана» → «Усунена» (підрядник)
    «Нова» / «Прийнята» → «Відхилена» (лише з причиною, БП-3)

«Виконана» ставиться не через PATCH /status, а під час здачі робіт з фото «після»
й актом (WORK_ORDER_ONLY, KAN-121).

Для кожного переходу вказано ролі, яким він дозволений. Модуль не звертається
до БД, тому правила можна перевірити звичайними тестами без бази.
"""

from dataclasses import dataclass

from app.core.enums import AccessRole, RequestStatus

NEW = RequestStatus.NEW
ACCEPTED = RequestStatus.ACCEPTED
IN_PROGRESS = RequestStatus.IN_PROGRESS
DONE = RequestStatus.DONE
RESOLVED = RequestStatus.RESOLVED
REJECTED = RequestStatus.REJECTED

# Працівники служби: диспетчер (operator, dispatcher) і дорожня поліція.
SERVICE_STAFF = frozenset({AccessRole.DISPATCHER, AccessRole.POLICE})
CONTRACTOR = frozenset({AccessRole.CONTRACTOR})

# (з якого, на який) -> ролі, яким перехід дозволено.
TRANSITIONS: dict[tuple[RequestStatus, RequestStatus], frozenset[AccessRole]] = {
    (NEW, ACCEPTED): SERVICE_STAFF,
    (NEW, REJECTED): SERVICE_STAFF,
    # Відхилення після перевірки на місці («не підтверджено на місці», UC-02 A2).
    (ACCEPTED, REJECTED): SERVICE_STAFF,
    # «Роботи розпочато»: служба власними силами або призначений підрядник (UC-04, крок 3).
    (ACCEPTED, IN_PROGRESS): SERVICE_STAFF | CONTRACTOR,
    (IN_PROGRESS, RESOLVED): SERVICE_STAFF,
    # «Виконана» ставить лише підрядник після 100 % і акта (UC-04, крок 4).
    (IN_PROGRESS, DONE): CONTRACTOR,
    # «Усунена» - лише служба після перевірки фотозвіту (БП-6).
    (DONE, RESOLVED): SERVICE_STAFF,
}

# Переходи, які не можна зробити через PATCH /reports/{id}/status, лише окремою дією.
# «Виконана» - тільки під час здачі робіт POST /work-orders/{id}/progress з прогресом
# 100 %, фото «після» й актом (DQ-08, БП-6, KAN-121); інакше акт можна обійти.
WORK_ORDER_ONLY: dict[tuple[RequestStatus, RequestStatus], str] = {
    (IN_PROGRESS, DONE): (
        "Статус «Виконана» ставиться під час здачі робіт: вкажіть прогрес 100 % "
        "і додайте фото «після» та акт виконаних робіт"
    ),
}

# Кінцеві статуси: після них заявка закривається (closed_at, БП-4).
FINAL_STATUSES = frozenset({RESOLVED, REJECTED})

STATUS_LABELS: dict[RequestStatus, str] = {
    NEW: "Нова",
    ACCEPTED: "Прийнята",
    IN_PROGRESS: "В роботі",
    DONE: "Виконана",
    RESOLVED: "Усунена",
    REJECTED: "Відхилена",
}


def next_statuses(current: RequestStatus, role: AccessRole | None = None) -> list[RequestStatus]:
    """Статуси, у які можна перейти з поточного (для ролі role або для будь-кого).

    Для ролі це кнопки PATCH /status у кабінеті, тому переходи з WORK_ORDER_ONLY
    (вони робляться окремою дією) до списку не входять.
    """
    return [
        to
        for (frm, to), roles in TRANSITIONS.items()
        if frm == current and (role is None or (role in roles and (frm, to) not in WORK_ORDER_ONLY))
    ]


@dataclass(frozen=True)
class TransitionCheck:
    """Результат перевірки переходу.

    allowed_status - чи існує такий перехід узагалі (інакше 409);
    allowed_role - чи може його зробити ця роль (інакше 403, БП-6).
    """

    allowed_status: bool
    allowed_role: bool
    message: str = ""

    @property
    def ok(self) -> bool:
        return self.allowed_status and self.allowed_role


def check_transition(
    current: RequestStatus, target: RequestStatus, role: AccessRole
) -> TransitionCheck:
    if current == target:
        return TransitionCheck(False, False, f"Заявка вже має статус «{STATUS_LABELS[target]}»")
    roles = TRANSITIONS.get((current, target))
    if roles is None:
        options = ", ".join(f"«{STATUS_LABELS[s]}»" for s in next_statuses(current)) or "немає"
        return TransitionCheck(
            False,
            False,
            f"Перехід «{STATUS_LABELS[current]}» → «{STATUS_LABELS[target]}» недопустимий. "
            f"Можливі переходи: {options}",
        )
    if role not in roles:
        return TransitionCheck(
            True,
            False,
            f"Статус «{STATUS_LABELS[target]}» не може поставити ця роль",
        )
    return TransitionCheck(True, True)
