import { Navigate } from "react-router-dom";

import { useMe } from "./api";
import { homePath } from "./redirect";

/** Корень `/`: отправляет вошедшего на главный экран его роли. */
export function HomeRedirect() {
  const { data: me } = useMe();
  if (me === undefined) return null;
  return <Navigate to={homePath(me.role)} replace />;
}
