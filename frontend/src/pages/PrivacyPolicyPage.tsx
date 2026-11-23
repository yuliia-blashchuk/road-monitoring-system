// KAN-110: сторінка «Політика приватності» (GDPR ст. 13; Закон України № 2297-VI).
// Джерела у звіті: підрозд. 3.5 (згоди), 3.7 (зберігання й видалення), табл. 11, 18, 24.
// Позначки «Реалізовано» / «Заплановано» мають відповідати стану коду - оновлюйте їх разом з ним.
import { Link } from 'react-router'

import {
  BROWSER_STORAGE,
  PRIVACY_POLICY_DATE,
  PRIVACY_POLICY_VERSION,
  openCookieSettings,
} from '../privacy/cookieConsent'

import './PrivacyPolicyPage.css'

type Status = 'done' | 'planned' | 'partial'

const STATUS_LABEL: Record<Status, string> = {
  done: 'Реалізовано',
  partial: 'Частково',
  planned: 'Заплановано',
}

function StatusBadge({ status }: { status: Status }) {
  return (
    <span className={`rm-privacy-status rm-privacy-status--${status}`}>{STATUS_LABEL[status]}</span>
  )
}

const DATA_CATEGORIES = [
  {
    category: 'Обліковий запис',
    data: 'Email, ім’я, телефон (необов’язково), хеш пароля, роль',
    purpose: 'Вхід, зв’язок заявок з автором, сповіщення про статус',
    basis: 'Згода водія (personal_data); для працівників служб і підрядників - договір',
  },
  {
    category: 'Заявка (публічні поля)',
    data: 'Тип проблеми, точка на карті, адреса, статус, дати, кількість підтверджень',
    purpose: 'Публічна карта стану доріг і робота служб',
    basis: 'Знеособлені дані; публічні після створення заявки',
  },
  {
    category: 'Фото й коментар',
    data: 'До 3 фото (без EXIF-метаданих) і коментар до 300 символів',
    purpose: 'Щоб служба зрозуміла проблему й перевірила ремонт',
    basis: 'Окрема згода media_sharing; без неї служба бачить лише публічні поля',
  },
  {
    category: 'Підтвердження «Теж бачу»',
    data: 'Хто й коли підтвердив заявку',
    purpose: 'Один голос від водія, підвищення пріоритету після 5 підтверджень',
    basis: 'Згода personal_data',
  },
  {
    category: 'Згоди',
    data: 'Тип згоди, версія тексту, дата надання й відкликання',
    purpose: 'Доказ законності обробки',
    basis: 'Юридичний обов’язок володільця даних',
  },
  {
    category: 'Журнал аудиту',
    data: 'Хто, коли й що зробив, роль, IP-адреса, результат; email маскується',
    purpose: 'Безпека, розслідування інцидентів, контроль доступу до даних',
    basis: 'Законний інтерес і вимоги до захисту інформації',
  },
  {
    category: 'Сповіщення',
    data: 'Текст сповіщення про зміну статусу вашої заявки',
    purpose: 'Повідомити автора про хід розгляду',
    basis: 'Згода personal_data; лист на email - окрема згода email_notifications',
  },
]

const RETENTION = [
  {
    data: 'Заявка: тип, точка, статус, дати',
    term: 'Безстроково',
    after: 'Лишається в статистиці без автора',
  },
  {
    data: 'Автор заявки, коментар, підтвердження',
    term: '6 місяців після закриття заявки',
    after: 'Зв’язок з автором видаляється, коментар стирається',
  },
  {
    data: 'Оригінали фото «до»',
    term: '90 днів після закриття',
    after: 'Видаляються; лишається розмита копія',
  },
  {
    data: 'Розмита копія фото, фото «після», акти робіт',
    term: '3 роки після закриття',
    after: 'Видаляються',
  },
  { data: 'Сповіщення', term: '90 днів', after: 'Видаляються' },
  {
    data: 'Акаунт водія',
    term: 'Поки акаунт активний; після 2 років без входу - попередження',
    after: 'Через 30 днів після попередження видаляється',
  },
  { data: 'Згоди', term: 'Строк дії акаунта + 3 роки', after: 'Видаляються' },
  { data: 'Журнал аудиту', term: '2 роки', after: 'Видаляється службовою процедурою' },
  { data: 'Резервні копії', term: '30 днів', after: 'Перезаписуються' },
]

const RECIPIENTS = [
  {
    who: 'Служба (диспетчер комунальної служби, дорожня поліція)',
    gets: 'Заявку з псевдонімом автора «Заявник #…» замість імені й контактів. Фото й коментар - лише якщо ви дали згоду media_sharing.',
    status: 'done' as Status,
  },
  {
    who: 'Підрядник',
    gets: 'Лише призначений йому об’єкт ремонту: тип, місце, строк. Без автора, коментаря й контактів водія.',
    status: 'done' as Status,
  },
  {
    who: 'Публічна карта (усі відвідувачі)',
    gets: 'Тільки публічні поля заявки: тип, точка, статус, дати, кількість підтверджень.',
    status: 'done' as Status,
  },
  {
    who: 'Диспетчер для уточнення',
    gets: 'Ваш email або телефон - лише за окремою згодою contact.',
    status: 'planned' as Status,
  },
  {
    who: 'OpenStreetMap',
    gets: 'Браузер завантажує з їхніх серверів зображення карти. Вони отримують лише технічні дані запиту (IP-адресу, браузер), як будь-який сайт. RoadMap не передає їм ваших даних.',
    status: 'done' as Status,
  },
]

const RIGHTS = [
  {
    right: 'Знати, які дані обробляються',
    how: 'Ця сторінка; дані профілю - у розділі «Профіль».',
    status: 'partial' as Status,
  },
  {
    right: 'Змінити вибір щодо cookie',
    how: 'Посилання «Налаштування cookie» внизу кожної сторінки.',
    status: 'done' as Status,
  },
  {
    right: 'Відкликати згоди сервісу (media_sharing, contact, email-сповіщення)',
    how: 'Сервер уже приймає відкликання (API «Мої згоди») і застосовує його одразу для наступних передач даних; сторінка «Мої згоди» в інтерфейсі - заплановано.',
    status: 'partial' as Status,
  },
  {
    right: 'Видалити акаунт',
    how: 'Запит з профілю: акаунт деактивується одразу, дані видаляються не пізніше ніж за місяць.',
    status: 'planned' as Status,
  },
  {
    right: 'Отримати копію своїх даних',
    how: 'Вивантаження профілю, заявок і згод з профілю.',
    status: 'planned' as Status,
  },
  {
    right: 'Подати скаргу',
    how: 'До Уповноваженого Верховної Ради України з прав людини (контролює захист персональних даних в Україні).',
    status: null,
  },
]

const SAFEGUARDS: { text: string; status: Status }[] = [
  { text: 'Паролі зберігаються лише як хеш Argon2id', status: 'done' },
  {
    text: 'Доступ за ролями (RBAC): кожна роль бачить лише свої дані, сервер перевіряє права на кожному запиті',
    status: 'done',
  },
  { text: 'З фото видаляються метадані EXIF (GPS, модель телефона, час)', status: 'done' },
  { text: 'Журнал аудиту не можна змінити чи видалити з застосунку', status: 'done' },
  { text: 'Перевірка згоди перед створенням заявки й надсиланням листів', status: 'done' },
  { text: 'Розмиття облич і номерів на публічних фото', status: 'planned' },
  { text: 'Автоматичне видалення й знеособлення даних за термінами', status: 'planned' },
]

function PrivacyPolicyPage() {
  return (
    <article className="rm-privacy" aria-labelledby="rm-privacy-title">
      <header className="rm-privacy__header">
        <p className="rm-privacy__eyebrow">RoadMap</p>
        <h1 id="rm-privacy-title">Політика приватності</h1>
        <p className="rm-privacy__meta">
          Версія {PRIVACY_POLICY_VERSION} від{' '}
          {new Date(PRIVACY_POLICY_DATE).toLocaleDateString('uk-UA')}
        </p>
        <p className="rm-privacy__lead">
          Тут простими словами пояснено, які дані збирає RoadMap, навіщо, кому їх видно і як довго
          вони зберігаються. Ми прямо позначаємо, що вже працює в прототипі, а що лише заплановано.
        </p>
      </header>

      <section aria-labelledby="privacy-controller">
        <h2 id="privacy-controller">1. Хто обробляє дані</h2>
        <p>
          RoadMap - навчальний проєкт: прототип системи, у якій водії повідомляють про проблеми на
          дорогах, а служби їх усувають. Зараз даними розпоряджається команда проєкту, а за захист
          даних відповідає роль Data Governance. У реальному впровадженні володільцем даних була б
          міська рада або уповноважене нею комунальне підприємство, і тут було б вказано його назву
          та контакти відповідальної особи.
        </p>
      </section>

      <section aria-labelledby="privacy-data">
        <h2 id="privacy-data">2. Які дані ми обробляємо і навіщо</h2>
        <div className="rm-privacy__table-wrap">
          <table>
            <caption className="rm-visually-hidden">
              Категорії даних, мета й правова підстава
            </caption>
            <thead>
              <tr>
                <th scope="col">Категорія</th>
                <th scope="col">Що саме</th>
                <th scope="col">Навіщо</th>
                <th scope="col">Правова підстава</th>
              </tr>
            </thead>
            <tbody>
              {DATA_CATEGORIES.map((row) => (
                <tr key={row.category}>
                  <th scope="row">{row.category}</th>
                  <td>{row.data}</td>
                  <td>{row.purpose}</td>
                  <td>{row.basis}</td>
                </tr>
              ))}
            </tbody>
          </table>
        </div>
        <p>
          Ми не збираємо більше, ніж потрібно: телефон необов’язковий, фото очищуються від
          метаданих, а службі замість імені автора показується псевдонім.
        </p>
      </section>

      <section aria-labelledby="privacy-browser">
        <h2 id="privacy-browser">3. Cookie та дані у вашому браузері</h2>
        <p>
          RoadMap <strong>не встановлює cookie</strong>. У браузері зберігаються лише технічно
          необхідні записи, для яких згода не потрібна. Додаткових (аналітичних) cookie чи скриптів
          зараз немає; якщо вони з’являться, ми завантажимо їх лише після вашої згоди.
        </p>
        <div className="rm-privacy__table-wrap">
          <table>
            <caption className="rm-visually-hidden">Дані, які RoadMap зберігає в браузері</caption>
            <thead>
              <tr>
                <th scope="col">Назва</th>
                <th scope="col">Де</th>
                <th scope="col">Категорія</th>
                <th scope="col">Навіщо</th>
                <th scope="col">Термін</th>
              </tr>
            </thead>
            <tbody>
              {BROWSER_STORAGE.map((item) => (
                <tr key={item.name}>
                  <th scope="row">
                    <code>{item.name}</code>
                  </th>
                  <td>{item.storage}</td>
                  <td>{item.category === 'necessary' ? 'Необхідні' : 'Додаткові'}</td>
                  <td>{item.purpose}</td>
                  <td>{item.lifetime}</td>
                </tr>
              ))}
            </tbody>
          </table>
        </div>
        <p>
          <button
            type="button"
            className="rm-privacy__button"
            onClick={openCookieSettings}
            aria-haspopup="dialog"
          >
            Змінити налаштування cookie
          </button>
        </p>
      </section>

      <section aria-labelledby="privacy-recipients">
        <h2 id="privacy-recipients">4. Кому передаються дані</h2>
        <ul className="rm-privacy__list">
          {RECIPIENTS.map((item) => (
            <li key={item.who}>
              <div>
                <strong>{item.who}.</strong> {item.gets}
              </div>
              <StatusBadge status={item.status} />
            </li>
          ))}
        </ul>
        <p>Ми не продаємо даних, не використовуємо їх для реклами і не передаємо за кордон.</p>
      </section>

      <section aria-labelledby="privacy-retention">
        <h2 id="privacy-retention">
          5. Як довго зберігаються дані <StatusBadge status="planned" />
        </h2>
        <p>
          Терміни нижче визначено правилами проєкту. Автоматичне видалення й знеособлення за ними ще
          не реалізоване в прототипі.
        </p>
        <div className="rm-privacy__table-wrap">
          <table>
            <caption className="rm-visually-hidden">Терміни зберігання даних</caption>
            <thead>
              <tr>
                <th scope="col">Дані</th>
                <th scope="col">Термін</th>
                <th scope="col">Що відбувається потім</th>
              </tr>
            </thead>
            <tbody>
              {RETENTION.map((row) => (
                <tr key={row.data}>
                  <th scope="row">{row.data}</th>
                  <td>{row.term}</td>
                  <td>{row.after}</td>
                </tr>
              ))}
            </tbody>
          </table>
        </div>
      </section>

      <section aria-labelledby="privacy-rights">
        <h2 id="privacy-rights">6. Ваші права</h2>
        <ul className="rm-privacy__list">
          {RIGHTS.map((item) => (
            <li key={item.right}>
              <div>
                <strong>{item.right}.</strong> {item.how}
              </div>
              {item.status && <StatusBadge status={item.status} />}
            </li>
          ))}
        </ul>
        <p>
          Відкликання згоди не робить незаконною обробку, що відбулася до нього. Відкликання
          обов’язкової згоди на обробку персональних даних означає запит на видалення акаунта.
        </p>
      </section>

      <section aria-labelledby="privacy-security">
        <h2 id="privacy-security">7. Як ми захищаємо дані</h2>
        <ul className="rm-privacy__list">
          {SAFEGUARDS.map((item) => (
            <li key={item.text}>
              <div>{item.text}</div>
              <StatusBadge status={item.status} />
            </li>
          ))}
        </ul>
      </section>

      <section aria-labelledby="privacy-changes">
        <h2 id="privacy-changes">8. Зміни цієї політики</h2>
        <p>
          Якщо зміниться склад даних у браузері або ця політика, ми оновимо версію, і банер згоди
          з’явиться знову, щоб ви могли зробити вибір заново.
        </p>
      </section>

      <p className="rm-privacy__back">
        <Link to="/">← Повернутися до карти</Link>
      </p>
    </article>
  )
}

export default PrivacyPolicyPage
