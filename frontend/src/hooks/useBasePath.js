import { useAuth } from '../context/AuthContext'
import { ROLE_HOME } from '../utils/roles'

/** '/admin' or '/lead' – lets shared pages link within the current role's route tree. */
export default function useBasePath() {
  const { user } = useAuth()
  return ROLE_HOME[user.role]
}
