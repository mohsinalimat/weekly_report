# Copyright (c) 2022, abayomi.awosusi@sgatechsolutions.com and contributors
# For license information, please see license.txt

import frappe
import calendar
import numpy as np
import json
import csv
import pandas as pd
from frappe import _, scrub
from frappe.utils import add_days, add_to_date, flt, getdate
from six import iteritems
from erpnext.accounts.utils import get_fiscal_year
from datetime import date

#
def execute(filters=None):
    return WeeklySales(filters).run()

#
class WeeklySales(object):

    #
    def __init__(self, filters=None):
        self.filters = frappe._dict(filters or {})
        self.date_field = ("transaction_date")
        self.months = ["Jan", "Feb", "Mar", "Apr", "May", "Jun", "Jul", "Aug", "Sep", "Oct", "Nov", "Dec"]
        self.get_period_date_ranges()

    #
    def run(self):
        self.get_columns()
        self.get_data()
    
        # Skipping total row for tree-view reports
        skip_total_row = 0
    
        return self.columns, self.data, None, None, skip_total_row

    #
    def get_columns(self):
        self.columns = [
            {
                "label": self.filters.cost_center, 
                "fieldname": "cost_center", 
                "fieldtype": "data", 
                "width": 140, 
                "hidden":1
            }
        ]
        self.columns.append (
            {
                "label": "Backlog", 
                "fieldname": "Backlog", 
                "fieldtype": "data", 
                "width": 120
            }
        )
        for end_date in self.periodic_daterange:
            period = self.get_period(end_date)
            self.columns.append(
                {
                    "label": _(period), 
                    "fieldname": scrub(period), 
                    "fieldtype": "Float", 
                    "width": 120
                }
            )
        self.columns.append (
            {"label": _("Total"), "fieldname": "total", "fieldtype": "Float", "width": 120}
        )

    #
    def get_data(self):
        self.get_sales_transactions_based_on_cost_center()
        self.get_rows()

        value_field = "base_net_total as value_field"
        entity = "project as entity"
        
    #
    def get_sales_transactions_based_on_cost_center(self):
        value_field = "base_amount"
        # self.entries = frappe.db.sql(
        # 	  """
        # 	  SELECT DISTINCT
        #         `tabSales Order`.grand_total, 
        #         `tabSales Order`.cost_center, 
        #         `tabSales Order`.name, 
        #         `tabSales Order`.transaction_date, 
        # 	      `tabSales Order`.customer_name, 
        #         `tabSales Order`.status, 
        #         `tabSales Order`.delivery_status, 
        # 	      `tabSales Order`.billing_status, 
        #         `tabSales Order Item`.item_group AS entity, 
        # 	      `tabSales Order Item`.base_amount AS value_field, 
        #         `tabSales Order Item`.delivery_date 
        #     FROM 
        #         `tabSales Order`, 
        # 	      `tabSales Order Item` 
        #     WHERE 
        #         `tabSales Order`.name = `tabSales Order Item`.parent  
        # 	      AND `tabSales Order`.status <> 'Cancelled' 
        #         AND `tabSales Order`.cost_center = %(cost_center)s 
        #         AND `tabSales Order Item`.delivery_date <=  %(to_date)s
        #     """, {
        # 		'cost_center': self.filters.cost_center, 'from_date': self.filters.start_date, 'to_date':  self.filters.to_date
        # 	}, 
        # 	as_dict=1, 
        # )	

        # self.get_groups()	

        self.entries = frappe.db.sql (
            """
            SELECT DISTINCT
                s.cost_center AS entity, 
                i.base_amount AS value_field, 
                s.transaction_date
            FROM    
                `tabSales Order` s, 
                `tabSales Order Item` i 
            WHERE 
                s.name = i.parent
                AND s.status <> 'Cancelled'
                AND s.cost_center = %(cost_center)s
                AND i.delivery_date <= %(to_date)s
            """, {
                'cost_center': self.filters.cost_center, 'from_date': self.filters.start_date, 'to_date':  self.filters.to_date
            }, as_dict=1, 
        )

    def get_rows(self):
        self.data = []
        self.get_periodic_data()
        self.get_period_rowweek_ranges()
        for entity, period_data in iteritems(self.entity_periodic_data):
            
            row = {
                "entity": entity, 
                "entity_name": self.entity_names.get(entity) if hasattr(self, "entity_names") else None, 
            }
            total = 0
            for end_date in self.week_periodic_daterange:
                period = self.get_weekperiod(end_date)
                amount = flt(period_data.get(period, 0.0))
                row[scrub(period)] = amount
                total += amount

            row["total"] = total

            self.data.append(row)
    def get_period_rowweek_ranges(self):
        from dateutil.relativedelta import MO, relativedelta

        from_date, to_date = getdate(self.filters.from_date), getdate(self.filters.to_date)

        increment = {"Monthly": 1, "Quarterly": 3, "Half-Yearly": 6, "Yearly": 12}.get(
            self.filters.range, 1
        )

        if self.filters.range in ["Monthly", "Quarterly", "Weekly"]:
            from_date = from_date.replace(day=1)
        elif self.filters.range == "Yearly":
            from_date = get_fiscal_year(from_date)[1]
        else:
            from_date = from_date + relativedelta(from_date, weekday=MO(-1))

        self.week_periodic_daterange = []
        for dummy in range(1, 53):
            if self.filters.range == "Weekly":
                period_end_date = add_days(from_date, 6)
            else:
                period_end_date = add_to_date(from_date, months=increment, days=-1)

            if period_end_date > to_date:
                period_end_date = to_date

            self.week_periodic_daterange.append(period_end_date)

            from_date = add_days(period_end_date, 1)
            if period_end_date == to_date:
                break


    def get_periodic_data(self):
        self.entity_periodic_data = frappe._dict()
        if self.filters.range == "Weekly":
            for d in self.entries:
                period = self.get_weekperiod(d.get(self.date_field))
                self.entity_periodic_data.setdefault(d.entity, frappe._dict()).setdefault(period.split('@')[0], 0.0)
                self.entity_periodic_data[d.entity][period.split('@')[0]] += flt(d.value_field)


    def get_period(self, posting_date):
        calendar.setfirstweekday(5)
        if self.filters.range == "Weekly":
            mnthname= posting_date.strftime('%b')
            x = np.array(calendar.monthcalendar(posting_date.year, posting_date.month)) 
            week_of_month = np.where(x == posting_date.day)[0][0] + 1
            period = mnthname +"-"+ str(posting_date.year)[-2:]

        return period


    def get_weekperiod(self, posting_date):
        calendar.setfirstweekday(5)
        if self.filters.range == "Weekly":
            mnthname= posting_date.strftime('%b')
            x = np.array(calendar.monthcalendar(posting_date.year, posting_date.month)) 
            week_of_month = np.where(x == posting_date.day)[0][0] + 1
            weekperiod= "Week " + str(week_of_month) +"@"+mnthname +"-"+ str(posting_date.year)[-2:]
        return weekperiod

    #for setting column month or week wise
    def get_period_date_ranges(self):
        from dateutil.relativedelta import MO, relativedelta

        from_date, to_date = getdate(self.filters.from_date), getdate(self.filters.to_date)

        increment = {"Monthly": 1, "Quarterly": 3, "Half-Yearly": 6, "Yearly": 12}.get(
            self.filters.range, 1
        )

        if self.filters.range in ["Monthly", "Quarterly", "Weekly"]:
            from_date = from_date.replace(day=1)
        elif self.filters.range == "Yearly":
            from_date = get_fiscal_year(from_date)[1]
        else:
            from_date = from_date + relativedelta(from_date, weekday=MO(-1))

        self.periodic_daterange = []
        for dummy in range(1, 53):
            if self.filters.range == "Week":
                period_end_date = add_days(from_date, 6)
            else:
                period_end_date = add_to_date(from_date, months=increment, days=-1)

            if period_end_date > to_date:
                period_end_date = to_date

            self.periodic_daterange.append(period_end_date)

            from_date = add_days(period_end_date, 1)
            if period_end_date == to_date:
                break
    
sales_allrecord=[]
@frappe.whitelist()
def get_monthly_report_record(report_name, filters):
    from dateutil.relativedelta import MO, relativedelta
    # Skipping total row for tree-view reports
    skip_total_row = 0    
    filterDt= json.loads(filters)
    filters = frappe._dict(filterDt or {})
    
    if filters.to_date:
        end_date= filters.to_date
    else:
        end_date= date.today()
    
    fiscalyeardt= fetch_selected_fiscal_year(end_date)
    for fy in fiscalyeardt:
        start_date=fy.get('year_start_date').strftime('%Y-%m-%d')
        fiscal_endDt=fy.get('year_end_date').strftime('%Y-%m-%d')

    filters.update({"fiscal_endDt":fiscal_endDt})
    filters.update({"from_date":start_date})
    coycostcenters = getcostcenters(filters)
    fiscalyeardtprev, prevyrsstartdate = fetch5yrsback_fiscalyear(5, filters)

    if filters.cost_center:
        sales_allrecord = frappe.db.sql (
            """
            SELECT 
                X.* 
            FROM (
                SELECT 
                    'Consolidated' AS entity, 
                    i.base_amount AS value_field, 
                    s.transaction_date, 
                    s.company 
                FROM
                    `tabSales Order` s, 
                    `tabSales Order Item` i 
                WHERE 
                    s.name = i.parent 
                    AND s.status <> 'Cancelled'
                    AND s.delivery_status='Not Delivered'
                    AND s.billing_status='Not Billed'
                    AND s.cost_center = %(cost_center)s
                    AND s.transaction_date between %(from_date)s
                    AND %(to_date)s

                UNION

                SELECT 
                    s.cost_center AS entity, 
                    s.transaction_date, 
                    s.company
                    i.base_amount AS value_field, 
                FROM 
                    `tabSales Order` s, 
                    `tabSales Order Item` i 
                WHERE 
                    s.name = i.parent
                    AND s.status <> 'Cancelled'
                    AND s.delivery_status='Not Delivered'
                    AND s.billing_status='Not Billed
                    AND s.cost_center = %(cost_center)s
                    AND s.transaction_date between %(from_date)s
                    AND %(to_date)s 
            ) X
            """, {
                'cost_center': filters.cost_center, 'from_date': filters.from_date, 'to_date': end_date
            }, as_dict=1, 
        )

        min_date_backlog = frappe.db.sql (
            """
            SELECT 
                M.*
            FROM (
                SELECT 
                    CONCAT(DATE_FORMAT(s.transaction_date, %(b)s), "-", RIGHT(fy.year, 2)) AS Date, 
                    fy.year AS year, 
                    sum(i.base_amount) AS TotalAmt, 
                    'Consolidated' AS cost_center
                FROM 
                    `tabSales Order` s, 
                    `tabSales Order Item` i, 
                    `tabFiscal Year` fy 
                WHERE 
                    s.name = i.parent
                    AND s.status <> 'Cancelled'
                    AND s.delivery_status='Not Delivered' 
                    AND s.billing_status='Not Billed'
                    AND s.transaction_date < %(before_date)s 
                    AND s.transaction_date >= %(prevstart_date)s 
                    AND s.transaction_date >= fy.year_start_date AND s.transaction_date <= fy.year_end_date 
                    AND s.cost_center = %(cost_center)s
                GROUP BY 
                    month(s.transaction_date), 
                    fy.year

                UNION

                SELECT 
                    CONCAT(DATE_FORMAT(s.transaction_date, %(b)s), "-", RIGHT(fy.year, 2)) AS Date, 
                    fy.year AS year, 
                    sum(i.base_amount) AS TotalAmt, 
                    s.cost_center
                FROM 
                    `tabSales Order` s, 
                    `tabSales Order Item` i, 
                    `tabFiscal Year` fy
                WHERE 
                    s.name = i.parent
                    AND s.status <> 'Cancelled
                    AND s.delivery_status='Not Delivered'
                    AND s.billing_status='Not Billed
                    AND s.transaction_date < %(before_date)s
                    AND s.transaction_date >= %(prevstart_date)s
                    AND s.transaction_date >= fy.year_start_date
                    AND s.transaction_date <= fy.year_end_date
                    AND s.cost_center = %(cost_center)s
                GROUP BY 
                    month(s.transaction_date), fy.year, s.cost_center
            ) M
            """, {
                'before_date': start_date, 'b':'%b', 'cost_center': filters.cost_center, 'Y':'%y', 'prevstart_date' : prevyrsstartdate
            }, as_dict=1, 
        )
    else:
        sales_allrecord = frappe.db.sql (
            """
            SELECT 
                X.*
            FROM (
                    SELECT 'Consolidated' AS entity, 
                    i.base_amount AS value_field, 
                    s.transaction_date, 
                    s.company FROM `tabSales Order` s, 
                    `tabSales Order Item` i 
                WHERE 
                    s.name = i.parent
                    AND s.status <> 'Cancelled'
                    AND s.delivery_status='Not Delivered'
                    AND s.billing_status='Not Billed'
                    AND s.transaction_date between %(from_date)s
                    AND %(to_date)s

                UNION

                SELECT 
                    i.base_amount AS value_field, 
                    s.cost_center AS entity, 
                    s.transaction_date, 
                    s.company
                FROM 
                    `tabSales Order` s, 
                    `tabSales Order Item` i 
                WHERE 
                    s.name = i.parent
                    AND s.status <> 'Cancelled'
                    AND s.delivery_status='Not Delivered'
                    AND s.billing_status='Not Billed'
                    AND s.transaction_date between %(from_date)s
                    AND %(to_date)s 
            ) X
            """, {
                'from_date': start_date, 'to_date': filters.to_date
            }, as_dict=1, 
        )

        min_date_backlog = frappe.db.sql (
            """
            SELECT 
                M.*
            FROM (
                SELECT 
                    CONCAT(DATE_FORMAT(s.transaction_date, %(b)s), "-", RIGHT(fy.year, 2)) AS Date, 
                    fy.year AS year, 
                    sum(i.base_amount) AS TotalAmt, 
                    'Consolidated' AS cost_center
                FROM 
                    `tabSales Order` s, 
                    `tabSales Order Item` i, 
                    `tabFiscal Year` fy 
                WHERE 
                    s.name = i.parent 
                    AND s.status <> 'Cancelled'
                    AND s.delivery_status='Not Delivered' 
                    AND s.billing_status='Not Billed' 
                    AND s.transaction_date < %(before_date)s 
                    AND s.transaction_date >= %(prevstart_date)s 
                    AND s.transaction_date >= fy.year_start_date 
                    AND s.transaction_date <= fy.year_end_date
                GROUP BY 
                    month(s.transaction_date), 
                    fy.year

                UNION

                SELECT 
                    CONCAT(DATE_FORMAT(s.transaction_date, %(b)s), "-", RIGHT(fy.year, 2)) AS Date, 
                    fy.year AS year, 
                    sum(i.base_amount) AS TotalAmt, 
                    s.cost_center
                FROM 
                    `tabSales Order` s, 
                    `tabSales Order Item` i, 
                    `tabFiscal Year` fy 
                WHERE 
                    s.name = i.parent 
                    AND s.status <> 'Cancelled'
                    AND s.delivery_status='Not Delivered' 
                    AND s.billing_status='Not Billed'
                    AND s.transaction_date < %(before_date)s 
                    AND s.transaction_date >= %(prevstart_date)s
                    AND s.transaction_date >= fy.year_start_date 
                    AND s.transaction_date <= fy.year_end_date
                GROUP BY
                    month(s.transaction_date), 
                    fy.year, 
                    s.cost_center
            ) M 
            """, {
                'before_date': start_date, 'b':'%b', 'Y':'%y', 'prevstart_date' : prevyrsstartdate
            }, as_dict=1, 
        )

    year_total_list = frappe._dict()
    for dd in min_date_backlog:
        year_total_list.setdefault(dd.cost_center, frappe._dict()).setdefault(dd.year, frappe._dict()).setdefault(dd.Date, dd.TotalAmt)
        year_total_list[dd.cost_center][dd.year][dd.Date] += flt(dd.TotalAmt)
    
    # check through all cost centers and prev yrs and see missing months and year and initialize to zero
    year_total_list2 = frappe._dict()
    for fy3 in fiscalyeardtprev: 
        fyr = fy3.year
        fsd = fy3.year_start_date
        fed = fy3.year_end_date
        currdt = fy3.year_start_date
        bkltotamt = 0.0
        i = 1

        while ((i < 13) and (currdt < fed)):
            i += 1
            mthyrstr = currdt.strftime("%b") + "-" + fyr[-2:]
            #take care of consolidated cost center
            #loop through all cost centers
            consolidatedcc = 'Consolidated'
            ccTotalAmt0 = 0

            for dd in min_date_backlog:
                if ((dd.cost_center==consolidatedcc) and (dd.Date==mthyrstr) and (dd.year==fyr)):
                    ccTotalAmt0 = dd.TotalAmt
            year_total_list2.setdefault(consolidatedcc, frappe._dict()).setdefault(fyr, frappe._dict()).setdefault(mthyrstr, ccTotalAmt0)
            year_total_list2[consolidatedcc][fyr][mthyrstr] += flt(ccTotalAmt0)

            if filters.cost_center:
                ccTotalAmt = 0
                cc = filters.cost_center
                for dd in min_date_backlog:
                    if ((dd.cost_center==cc) and (dd.Date==mthyrstr) and (dd.year==fyr)):
                        ccTotalAmt = dd.TotalAmt
                year_total_list2.setdefault(cc, frappe._dict()).setdefault(fyr, frappe._dict()).setdefault(mthyrstr, ccTotalAmt)
                year_total_list2[cc][fyr][mthyrstr] += flt(ccTotalAmt)
            else:
                for cc in coycostcenters:
                    ccTotalAmt = 0
                    for dd in min_date_backlog:
                        if ((dd.cost_center==cc) and (dd.Date==mthyrstr) and (dd.year==fyr)):
                            ccTotalAmt = dd.TotalAmt
                    year_total_list2.setdefault(cc, frappe._dict()).setdefault(fyr, frappe._dict()).setdefault(mthyrstr, ccTotalAmt)
                    year_total_list2[cc][fyr][mthyrstr] += flt(ccTotalAmt)

            currdt2 = currdt + relativedelta(months=+1)
            currdt = currdt2

    year_lis = list(year_total_list2.items())
    WSobj = WeeklySales()
    WSobj.__init__()
    compnyName=""
    if sales_allrecord:
        ftch_cmpny = {entry.get('company') for entry in sales_allrecord}
        compnyName=ftch_cmpny
        
    Cust_periodic_daterange=cust_get_period_date_ranges(filters)
    Cust_colum_name=cust_get_columns(filters, Cust_periodic_daterange)
    Cust_rows_values=cust_get_rows_forallweeks(filters, sales_allrecord, Cust_periodic_daterange, coycostcenters, start_date, fiscal_endDt)
    combined_list=[]
    combined_list.append((list(Cust_rows_values), year_lis))

    return Cust_colum_name, combined_list, compnyName

#
def cust_get_columns(filters, Cust_periodic_daterange):
    cust_columns=[
        {
            "label": "Backlog", 
            "fieldname": "Backlog", 
            "fieldtype": "data", 
            "width": 120
        }
    ]

    for end_date in Cust_periodic_daterange:
        period = cust_get_period(end_date, filters)
        cust_columns.append(
            {
                "label": _(period), 
                "fieldname": scrub(period), 
                "fieldtype": "Float", 
                "width": 120
            }
        )

    return cust_columns

#
def cust_get_period(posting_date, filters):
    period = ""
    calendar.setfirstweekday(5)

    if filters.range == "Weekly":
        mnthname= posting_date.strftime('%b')
        x = np.array(calendar.monthcalendar(posting_date.year, posting_date.month))
        week_of_month = np.where(x == posting_date.day)[0][0] + 1
        period = mnthname +"-"+ str(posting_date.year)[-2:]
        
    return period

#for setting column month from week wise
def cust_get_period_date_ranges(filters):
    from dateutil.relativedelta import MO, relativedelta
    from_date, to_date = getdate(filters.from_date), getdate(filters.fiscal_endDt)

    increment = {"Monthly": 1, "Quarterly": 3, "Half-Yearly": 6, "Yearly": 12}.get(
        filters.range, 1
    )
    
    if filters.range in ["Monthly", "Quarterly", "Weekly"]:
        from_date = get_fiscal_year(from_date)[1]
    elif filters.range == "Yearly":
        from_date = get_fiscal_year(from_date)[1]
    else:
        from_date = from_date + relativedelta(from_date, weekday=MO(-1))

    periodic_daterange = []
    for dummy in range(1, 53):
        if filters.range == "Week":
            period_end_date = add_days(from_date, 6)
        else:
            period_end_date = add_to_date(from_date, months=increment, days=-1)

        if period_end_date > to_date:
            period_end_date = to_date

        periodic_daterange.append(period_end_date)

        from_date = add_days(period_end_date, 1)
        if period_end_date == to_date:
            break
    return periodic_daterange

#
def cust_get_weekperiod(filters, posting_date):
    calendar.setfirstweekday(5)
    if filters.range == "Weekly":
        mnthname= posting_date.strftime('%b')
        x = np.array(calendar.monthcalendar(posting_date.year, posting_date.month))
        week_of_month = np.where(x == posting_date.day)[0][0] + 1
        #period = "Week " + str(posting_date.isocalendar()[1]) + " "+ mnthname +" "+ str(posting_date.year)
        weekperiod= "Week " + str(week_of_month) +"@"+mnthname +"-"+ str(posting_date.year)[-2:]

    return weekperiod


def cust_get_allweekperiods(filters, start_date, end_date):
    from dateutil.relativedelta import relativedelta
    data = []
    calendar.setfirstweekday(5)
    if filters.range == "Weekly":
        currdt = getdate(start_date)
        while (currdt <= getdate(end_date)):
            for x in range(1, 6):
                mnthname= currdt.strftime('%b')
                weekperiod= "Week " + str(x) +"@"+mnthname +"-"+ str(currdt.year)[-2:]
                data.append(weekperiod)
            currdt2 = currdt + relativedelta(months=+1)
            currdt = currdt2

    return data

#bind rows according to the record
def cust_get_rows(filters, records, Cust_periodic_daterange):
    data = []
    ## start get week from month
    entity_periodic_data = frappe._dict()
    if filters.range == "Weekly":
        for d in records:
            cust_period = cust_get_weekperiod(filters, d.transaction_date)
            entity_periodic_data.setdefault(d.entity, frappe._dict()).setdefault(cust_period, 0.0)
            entity_periodic_data[d.entity][cust_period] += flt(d.value_field)
        
    con_lis = list(entity_periodic_data.items())  #convert dict to list

    return con_lis


def cust_get_rows_forallweeks(filters, records, Cust_periodic_daterange, coycostcenters, from_date, to_date):
    data = []
    ## start get week from month
    entity_periodic_data = frappe._dict()
    if filters.range == "Weekly":
        # set all week periods
        cust_periods_list = cust_get_allweekperiods(filters, from_date, to_date)
        consolidcc = "Consolidated"

        for cp in cust_periods_list:
            ccTotalAmt0 = 0.0
            for d in records:
                cust_period = cust_get_weekperiod(filters, d.transaction_date)
                if ((consolidcc==d.entity) and (cp==cust_period)):
                    ccTotalAmt0 += flt(d.value_field)
                        
            entity_periodic_data.setdefault(consolidcc, frappe._dict()).setdefault(cp, ccTotalAmt0)
        
        if filters.cost_center:
            cc = filters.cost_center
            
            for cp in cust_periods_list:
                ccTotalAmt = 0.0
                for d in records:
                    cust_period = cust_get_weekperiod(filters, d.transaction_date)
                    if ((cc==d.entity) and (cp==cust_period)):
                        ccTotalAmt += flt(d.value_field)
                        
                entity_periodic_data.setdefault(cc, frappe._dict()).setdefault(cp, ccTotalAmt)
        else:
            for cc in coycostcenters:
                for cp in cust_periods_list:
                    ccTotalAmt = 0.0
                    for d in records:
                        cust_period = cust_get_weekperiod(filters, d.transaction_date)
                        if ((cc==d.entity) and (cp==cust_period)):
                            ccTotalAmt += flt(d.value_field)
                        
                    entity_periodic_data.setdefault(cc, frappe._dict()).setdefault(cp, ccTotalAmt)

    con_lis = list(entity_periodic_data.items())  #convert dict to list

    return con_lis    

# 
def fetch_selected_fiscal_year(end_date):
    fetch_fiscal_year_selection = frappe.db.sql(
        """
        SELECT 
            year_start_date, 
            year_end_date
        FROM
            `tabFiscal Year`
        WHERE
            %(Slct_date)s between year_start_date
            AND year_end_date
        """, {
            'Slct_date': end_date
        }, as_dict=1, 
    )

    return fetch_fiscal_year_selection


def fetch5yrsback_fiscalyear(noofyrsback, filters):
    if filters.to_date:
        end_date= filters.to_date
    else:
        end_date= date.today()

    fetch_fiscal_year_selection_1 = frappe.db.sql(
        """
        SELECT 
            year, 
            year_start_date, 
            year_end_date
        FROM 
            `tabFiscal Year` 
        WHERE  
            %(Slct_date)s BETWEEN year_start_date AND year_end_date
        """, {
            'Slct_date': end_date
        }, as_dict=1, 
    )

    curryr = 0
    prevyrsback = 0

    for ff in fetch_fiscal_year_selection_1:
        curryr = ff.year

    prevyrsback = int(curryr) - noofyrsback

    fetch_fiscal_year_selection = frappe.db.sql (
        """
        SELECT 
            year, 
            year_start_date, 
            year_end_date 
        FROM 
            `tabFiscal Year` 
        WHERE 
            year >= %(startyr)s
            AND year < %(endyr)s 
        ORDER BY 
            year ASC
        """, {
            'startyr': prevyrsback, 'endyr': curryr
        }, as_dict=1, 
    )  

    fetch_fiscal_year_selection_3 = frappe.db.sql (
        """
        SELECT 
            min(year_start_date) AS begindate 
        FROM 
            `tabFiscal Year` 
        WHERE 
            year >= %(startyr)s
            AND year < %(endyr)s
        """, {
            'startyr': prevyrsback, 'endyr': curryr
        }, as_dict=1, 
    )      
    for ff2 in fetch_fiscal_year_selection_3:
        prevyrsstartdate = ff2.begindate
    #print(prevyrsstartdate)
    return fetch_fiscal_year_selection, prevyrsstartdate


def getcostcenters(filters):
    cstcnt = [] # get function to fetch cost centers
    cstcnt0 = frappe.db.get_list("Cost Center", pluck='name', filters={'company': filters.company, 'is_group':0})

    # change the order of cost center this is customized for this client
    # specify order here 02, 03, 01, 06
    cstorder = ['02', '03', '06', '01']
    i = 0
    while(i<len(cstorder)):
        for cstr in cstcnt0:
            if (cstr.startswith(cstorder[i])):
                cstcnt.append(cstr)
        i+=1
        
    # if created cost centers increase
    if ((len(cstorder)<len(cstcnt0)) and (len(cstcnt)>0) ):
        for cstr2 in cstcnt0:
            cstfound = False
            for m in cstcnt:
                if (m==cstr2):
                    cstfound = True
            if (cstfound == False):
                 cstcnt.append(cstr2)         

    if (len(cstcnt)==0):
       cstcnt = cstcnt0 

    return cstcnt
