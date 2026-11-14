import { keepPreviousData, useQuery } from '@tanstack/react-query'
import { useState } from 'react'
import { Link } from 'react-router'

import { listAllUsers, listOrgs, listScans, type ScanFilters } from '../api/endpoints'
import { useAuth } from '../auth/AuthProvider'
import { Pagination } from '../components/Pagination'
import { Alert, Card, Field, Input, Select, Spinner } from '../components/ui'
import { formatUtc, oneLine } from '../lib/format'

export function ScanHistoryPage() {
  const { can } = useAuth()
  const [filters, setFilters] = useState<ScanFilters>({})
  const [page, setPage] = useState(1)
  const seeAll = can('view_all_scans')
  const seeTeam = seeAll || can('view_team_scans')

  const scans = useQuery({
    queryKey: ['scans', filters, page],
    queryFn: () => listScans(filters, page),
    placeholderData: keepPreviousData,
  })
  const orgs = useQuery({ queryKey: ['orgs'], queryFn: listOrgs, enabled: seeAll })
  const users = useQuery({ queryKey: ['users-all'], queryFn: listAllUsers, enabled: seeTeam })

  const update = (patch: ScanFilters) => { setFilters({ ...filters, ...patch }); setPage(1) }
  const toId = (v: string) => (v ? Number(v) : null)

  return (
    <div className="space-y-6">
      <div>
        <h1 className="text-2xl font-semibold">Scan history</h1>
        <p className="text-sm text-slate-500">
          {seeAll ? 'All organisations' : seeTeam ? 'Everyone in your organisation' : 'Your scans'}
        </p>
      </div>

      <Card className="grid gap-4 p-4 sm:grid-cols-2 lg:grid-cols-5">
        {seeAll && (
          <Field label="Organisation">
            <Select value={filters.org_id ?? ''} onChange={e => update({ org_id: toId(e.target.value), user_id: null })}>
              <option value="">All</option>
              {orgs.data?.map(o => <option key={o.id} value={o.id}>{o.name}</option>)}
            </Select>
          </Field>
        )}
        {seeTeam && (
          <Field label="Run by">
            <Select value={filters.user_id ?? ''} onChange={e => update({ user_id: toId(e.target.value) })}>
              <option value="">Anyone</option>
              {users.data?.filter(u => !filters.org_id || u.org_id === filters.org_id)
                .map(u => <option key={u.id} value={u.id}>{u.name}</option>)}
            </Select>
          </Field>
        )}
        <Field label="From">
          <Input type="date" value={filters.date_from ?? ''} onChange={e => update({ date_from: e.target.value })} />
        </Field>
        <Field label="To">
          <Input type="date" value={filters.date_to ?? ''} onChange={e => update({ date_to: e.target.value })} />
        </Field>
        <Field label="Job description contains">
          <Input value={filters.jd ?? ''} maxLength={100} onChange={e => update({ jd: e.target.value })} />
        </Field>
      </Card>

      {scans.isLoading && <Spinner />}
      {scans.error && <Alert tone="error">{scans.error.message}</Alert>}
      {scans.data && (scans.data.items.length === 0
        ? <Alert>No scans match these filters.</Alert>
        : (
          <>
            <Card className="overflow-x-auto">
              <table className="w-full text-left text-sm">
                <thead className="border-b border-slate-200 bg-slate-50 text-xs uppercase tracking-wide text-slate-500">
                  <tr>
                    <th className="px-4 py-3 font-medium">When</th>
                    <th className="px-4 py-3 font-medium">Job description</th>
                    <th className="px-4 py-3 font-medium">Resumes</th>
                    <th className="px-4 py-3 font-medium">Shortlisted</th>
                    {seeTeam && <th className="px-4 py-3 font-medium">Run by</th>}
                    {seeAll && <th className="px-4 py-3 font-medium">Organisation</th>}
                  </tr>
                </thead>
                <tbody className="divide-y divide-slate-100">
                  {scans.data.items.map(s => (
                    <tr key={s.id} className="hover:bg-slate-50">
                      <td className="whitespace-nowrap px-4 py-3">
                        <Link to={`/scans/${s.id}`} className="font-medium text-indigo-700 hover:underline">
                          {formatUtc(s.created_at)}
                        </Link>
                      </td>
                      <td className="px-4 py-3 text-slate-700">{oneLine(s.jd_text)}</td>
                      <td className="px-4 py-3">{s.resume_count}</td>
                      <td className="px-4 py-3">{s.shortlisted_count}</td>
                      {seeTeam && <td className="px-4 py-3">{s.run_by}</td>}
                      {seeAll && <td className="px-4 py-3">{s.org}</td>}
                    </tr>
                  ))}
                </tbody>
              </table>
            </Card>
            <Pagination page={page} pageSize={scans.data.page_size} total={scans.data.total} onPage={setPage} />
          </>
        ))}
    </div>
  )
}
