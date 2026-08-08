import { useEffect, useState } from "react";
import { useTranslation } from "react-i18next";

import {
  acceptClassroomInvite,
  fetchClassroomInvites,
  fetchMyStudents,
  fetchMyTeachers,
  inviteStudent,
  removeClassroomLink,
  type ClassroomInvite,
  type ClassroomStudent,
  type ClassroomTeacher,
} from "../auth/api";

type Tab = "students" | "teachers";

/** A teacher's roster (many students) and a student's consent-transparency
 * view (who's watching them) — the asymmetric, one-to-many counterpart to
 * the mutual, one-to-one StudyBuddyCard on Home. */
export default function Classroom() {
  const { t } = useTranslation();
  const [tab, setTab] = useState<Tab>("students");
  const [students, setStudents] = useState<ClassroomStudent[]>([]);
  const [teachers, setTeachers] = useState<ClassroomTeacher[]>([]);
  const [invites, setInvites] = useState<ClassroomInvite[]>([]);
  const [loading, setLoading] = useState(true);
  const [email, setEmail] = useState("");
  const [busy, setBusy] = useState(false);
  const [error, setError] = useState<string | null>(null);

  async function load() {
    setLoading(true);
    try {
      const [s, t, i] = await Promise.all([fetchMyStudents(), fetchMyTeachers(), fetchClassroomInvites()]);
      setStudents(s);
      setTeachers(t);
      setInvites(i);
    } catch (err) {
      setError(err instanceof Error ? err.message : t("common.error"));
    } finally {
      setLoading(false);
    }
  }

  useEffect(() => {
    load();
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, []);

  async function onInvite() {
    if (!email.trim() || busy) return;
    setBusy(true);
    setError(null);
    try {
      await inviteStudent(email.trim());
      setEmail("");
      await load();
    } catch (err) {
      setError(err instanceof Error ? err.message : t("common.error"));
    } finally {
      setBusy(false);
    }
  }

  async function onRemoveStudent(id: number) {
    setBusy(true);
    try {
      await removeClassroomLink(id);
      setStudents((s) => s.filter((x) => x.id !== id));
    } finally {
      setBusy(false);
    }
  }

  async function onAccept(id: number) {
    setBusy(true);
    try {
      await acceptClassroomInvite(id);
      await load();
    } catch (err) {
      window.alert(err instanceof Error ? err.message : t("common.error"));
    } finally {
      setBusy(false);
    }
  }

  async function onDeclineInvite(id: number) {
    setBusy(true);
    try {
      await removeClassroomLink(id);
      setInvites((i) => i.filter((x) => x.id !== id));
    } finally {
      setBusy(false);
    }
  }

  async function onRevokeTeacher(id: number) {
    setBusy(true);
    try {
      await removeClassroomLink(id);
      setTeachers((ts) => ts.filter((x) => x.id !== id));
    } finally {
      setBusy(false);
    }
  }

  if (loading) return <div className="panel">{t("common.loading")}</div>;

  return (
    <div className="classroom">
      <h1>{t("classroom.title")}</h1>

      <div className="segmented classroom__tabs">
        <button
          className={`segmented__btn ${tab === "students" ? "segmented__btn--on" : ""}`}
          aria-pressed={tab === "students"}
          onClick={() => setTab("students")}
        >
          {t("classroom.myStudents", { count: students.length })}
        </button>
        <button
          className={`segmented__btn ${tab === "teachers" ? "segmented__btn--on" : ""}`}
          aria-pressed={tab === "teachers"}
          onClick={() => setTab("teachers")}
        >
          {t("classroom.myTeachers", { count: teachers.length + invites.length })}
        </button>
      </div>

      {tab === "students" && (
        <div className="classroom__panel">
          <p className="buddycard__hint">{t("classroom.studentsHint")}</p>
          <div className="buddycard__row">
            <input
              className="input"
              type="email"
              placeholder={t("studyBuddy.emailPlaceholder")}
              value={email}
              onChange={(e) => setEmail(e.target.value)}
              onKeyDown={(e) => e.key === "Enter" && onInvite()}
            />
            <button className="btn btn--primary btn--sm" disabled={!email.trim() || busy} onClick={onInvite}>
              {busy ? t("classroom.inviting") : t("classroom.inviteBtn")}
            </button>
          </div>
          {error && <p className="auth__error">{error}</p>}

          {students.length === 0 ? (
            <p className="buddycard__hint">{t("classroom.noStudents")}</p>
          ) : (
            <ul className="classroom__list">
              {students.map((s) => (
                <li key={s.id} className="classroom__row">
                  <span className="classroom__email">{s.student_email}</span>
                  {s.status === "pending" ? (
                    <span className="classroom__status">{t("classroom.pending")}</span>
                  ) : (
                    s.student && (
                      <span className="classroom__stats">
                        {t("studyBuddy.todayCount", { count: s.student.today })}
                        {s.student.streak > 0 && <> · 🔥 {s.student.streak}</>}
                      </span>
                    )
                  )}
                  <button className="btn btn--ghost btn--sm" disabled={busy} onClick={() => onRemoveStudent(s.id)}>
                    {t("classroom.removeBtn")}
                  </button>
                </li>
              ))}
            </ul>
          )}
        </div>
      )}

      {tab === "teachers" && (
        <div className="classroom__panel">
          {invites.length > 0 && (
            <ul className="classroom__list">
              {invites.map((inv) => (
                <li key={inv.id} className="classroom__row">
                  <span className="classroom__email">{t("classroom.invitedYou", { email: inv.teacher_email })}</span>
                  <button className="btn btn--primary btn--sm" disabled={busy} onClick={() => onAccept(inv.id)}>
                    {t("studyBuddy.acceptBtn")}
                  </button>
                  <button className="btn btn--ghost btn--sm" disabled={busy} onClick={() => onDeclineInvite(inv.id)}>
                    {t("studyBuddy.declineBtn")}
                  </button>
                </li>
              ))}
            </ul>
          )}

          {teachers.length === 0 ? (
            <p className="buddycard__hint">{t("classroom.noTeachers")}</p>
          ) : (
            <ul className="classroom__list">
              {teachers.map((tch) => (
                <li key={tch.id} className="classroom__row">
                  <span className="classroom__email">{tch.teacher_email}</span>
                  <button className="btn btn--ghost btn--sm" disabled={busy} onClick={() => onRevokeTeacher(tch.id)}>
                    {t("classroom.revokeBtn")}
                  </button>
                </li>
              ))}
            </ul>
          )}
        </div>
      )}
    </div>
  );
}
