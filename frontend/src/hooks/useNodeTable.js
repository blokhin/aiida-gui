import { useState, useRef, useEffect, useCallback } from 'react';

const PAGE_SIZE_KEY = 'aiida-gui:pageSize';
const VALID_PAGE_SIZES = [15, 30, 100];

const DENSITY_KEY = 'aiida-gui:density';
const VALID_DENSITIES = ['compact', 'standard', 'comfortable'];

function readStoredPageSize() {
  try {
    const stored = localStorage.getItem(PAGE_SIZE_KEY);
    const value = stored ? Number(stored) : 30;
    return VALID_PAGE_SIZES.includes(value) ? value : 30;
  } catch {
    return 30;
  }
}

function writeStoredPageSize(pageSize) {
  try {
    localStorage.setItem(PAGE_SIZE_KEY, String(pageSize));
  } catch {}
}

function readStoredDensity() {
  try {
    const stored = localStorage.getItem(DENSITY_KEY);
    return VALID_DENSITIES.includes(stored) ? stored : 'standard';
  } catch {
    return 'standard';
  }
}

function writeStoredDensity(density) {
  try {
    localStorage.setItem(DENSITY_KEY, String(density));
  } catch {}
}

export default function useNodeTable(endpointBase) {
  const [rows, setRows]           = useState([]);
  const [rowCount, setRowCount]   = useState(0);
  const [pagination, _setPagination] = useState({ page: 0, pageSize: readStoredPageSize() });
  const setPagination = (model) => {
    _setPagination(prev => {
      const next = typeof model === 'function' ? model(prev) : model;
      writeStoredPageSize(next.pageSize);
      return next;
    });
  };
  const [density, _setDensity] = useState(readStoredDensity());
  const setDensity = (newDensity) => {
    _setDensity(prev => {
      const next = typeof newDensity === 'function' ? newDensity(prev) : newDensity;
      writeStoredDensity(next);
      return next;
    });
  };
  const [sortModel, setSortModel] = useState([{ field: 'pk', sort: 'desc' }]);
  const [filterModel, setFilter]  = useState({ items: [] });
  const isFetchingRef = useRef(false);
  /* hide description at first render – users can toggle in column menu */
  const [columnVisibilityModel, setColumnVisibilityModel] = useState({
    description: false,
    exit_status: false,
    exit_message: false,
    paused: false,
  });

  const fetchData = useCallback(() => {
    if (isFetchingRef.current) return;
    isFetchingRef.current = true;

    const { page, pageSize } = pagination;
    const skip  = page * pageSize;
    const sortField  = sortModel[0]?.field ?? 'pk';
    const sortOrder  = sortModel[0]?.sort  ?? 'desc';
    const url =
      `${endpointBase}-data?skip=${skip}&limit=${pageSize}` +
      `&sortField=${sortField}&sortOrder=${sortOrder}` +
      `&filterModel=${encodeURIComponent(JSON.stringify(filterModel))}`;

      fetch(url)
      .then(r => r.json())
      .then(({ data, total }) => {
        setRows(data);
        setRowCount(total);
      })
      .catch((e) => console.error("Fetch error", e))
      .finally(() => { isFetchingRef.current = false; });
  }, [endpointBase, pagination, sortModel, filterModel]);

  /* fetch on mount & whenever deps change */
  useEffect(() => {
    fetchData();
    const interval = setInterval(fetchData, 3000);
    return () => clearInterval(interval);
  }, [fetchData]);
  /* reset to page 0 when a filter changes */
  useEffect(() => { setPagination(p => ({ ...p, page: 0 })); }, [filterModel]);

  return {
    rows, rowCount,
    pagination, setPagination,
    density, setDensity,
    columnVisibilityModel, setColumnVisibilityModel,
    sortModel, setSortModel,
    filterModel, setFilter,
    refetch: fetchData,
  };
}
