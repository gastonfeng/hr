# -*- coding:utf-8 -*-
#
#
#    Copyright (C) 2011 Michael Telahun Makonnen <mmakonnen@gmail.com>.
#    All Rights Reserved.
#
#    This program is free software: you can redistribute it and/or modify
#    it under the terms of the GNU Affero General Public License as published
#    by the Free Software Foundation, either version 3 of the License, or
#    (at your option) any later version.
#
#    This program is distributed in the hope that it will be useful,
#    but WITHOUT ANY WARRANTY; without even the implied warranty of
#    MERCHANTABILITY or FITNESS FOR A PARTICULAR PURPOSE.  See the
#    GNU Affero General Public License for more details.
#
#    You should have received a copy of the GNU Affero General Public License
#    along with this program.  If not, see <http://www.gnu.org/licenses/>.
#
#

from datetime import datetime

import openerp.addons.decimal_precision as dp
from dateutil.relativedelta import relativedelta
from openerp import netsvc
from openerp.tools import DEFAULT_SERVER_DATE_FORMAT
from openerp.tools.translate import _

from odoo import models, fields


class wage_increment(models.Model):

    _name = 'hr.contract.wage.increment'
    _description = 'HR Contract Wage Adjustment'

    def _calculate_difference(
            self,  ids, field_name, args, context=None):

        res = dict.fromkeys(ids)
        for incr in self.browse( ids, context=context):
            if incr.wage >= incr.contract_id.wage:
                percent = ((incr.wage / incr.contract_id.wage) - 1.0) * 100.0
            else:
                percent = (1.0 - (incr.wage / incr.contract_id.wage)) * -100.0
            res[incr.id] = {
                'wage_difference': incr.wage - incr.current_wage,
                'wage_difference_percent': percent,
            }

        return res

    def _get_department(self,  ids, field_name, arg, context=None):

        res = dict.fromkeys(ids, False)
        for incr in self.browse( ids, context=context):
            res[incr.id] = incr.employee_id.department_id.id,

        return res

    effective_date = fields.Date('Effective Date', required=True, readonly=True,
                                 states={'draft': [('readonly', False)]}, )
    wage = fields.Float('New Wage', digits_compute=dp.get_precision('Payroll'), required=True, readonly=True,
                        states={'draft': [('readonly', False)]}, )
    new_contract_id = fields.Many2one('hr.contract', 'New Contract', readonly=True, )
    contract_id = fields.Many2one('hr.contract', 'Contract', readonly=True, )
    current_wage = fields.Float(related='contract_id.wage', type='float', string='Current Wage', store=True,
                                readonly=True, )
    wage_difference = fields.Float(compute='_calculate_difference', type='float', method=True, string='Difference',
                                   multi='diff', readonly=True, )
    wage_difference_percent = fields.Float(compute='_calculate_difference', type='float', method=True,
                                           string='Percentage', multi='diff', readonly=True, )
    employee_id = fields.Many2one(related='contract_id.employee_id', relation='hr.employee', type='many2one',
                                  string='Employee', store=True, readonly=True, )
    job_id = fields.Many2one(related='contract_id.job_id', relation='hr.job', type='many2one', string='Job', store=True,
                             readonly=True, )
    department_id = fields.Many2one(related='employee_id.department_id', relation='hr.department', type='many2one',
                                    string='Department', store=True, readonly=True, )
    state = fields.Selection(
        [('draft', 'Draft'), ('confirm', 'Confirmed'), ('approve', 'Approved'), ('decline', 'Declined')], 'State',
        readonly=True, )
    run_id = fields.Many2one('hr.contract.wage.increment.run', 'Batch Run', readonly=True, ondelete='cascade', )

    def _get_contract_data(self,  field_list, context=None):

        if context is None:
            context = {}
        employee_id = self._get_employee( context=context)
        ee_data = self.pool.get('hr.employee').read(
             employee_id, ['contract_id'], context=context)
        contract_id = ee_data.get('contract_id', False)[0]
        if not contract_id:
            return False

        data = self.pool.get('hr.contract').read(
             contract_id, field_list, context=context)

        return data

    def _get_contract_id(self,  context=None):

        data = self._get_contract_data( ['id'], context)
        return data.get('id', False)

    def _get_employee(self,  context=None):

        if context is None:
            context = {}
        employee_id = context.get('active_id', False)

        return employee_id

    def _get_effective_date(self,  context=None):

        contract_id = self._get_contract_id( context=context)
        if not contract_id:
            return False

        contract = self.pool.get('hr.contract').browse(
             contract_id, context=context)
        if contract.pps_id:
            first_day = 1
            if contract.pps_id.type == 'monthly':
                first_day = contract.pps_id.mo_firstday
            date_format = '%Y-%m-' + first_day
            dThisMonth = datetime.now().strftime(
                date_format).strptime(DEFAULT_SERVER_DATE_FORMAT).date()
            dNextMonth = (datetime.now() + relativedelta(months=+1)).strftime(
                date_format).strptime(DEFAULT_SERVER_DATE_FORMAT).date()
            if dThisMonth < datetime.now().date():
                return dNextMonth.strftime(DEFAULT_SERVER_DATE_FORMAT)
            else:
                return dThisMonth.strftime(DEFAULT_SERVER_DATE_FORMAT)

        return False

    _defaults = {
        'contract_id': _get_contract_id,
        'employee_id': _get_employee,
        'effective_date': _get_effective_date,
        'state': 'draft',
    }

    _rec_name = 'effective_date'

    def _check_state(self,  wage_incr, context=None):

        wage_incr_ids = self.search( [
            ('contract_id', '=', wage_incr.contract_id.id),
            ('state', 'in', [
                'draft', 'confirm', 'approved']),
            ('id', '!=', wage_incr.id),
        ],
            context=context)
        if len(wage_incr_ids) > 0:
            data = self.pool.get('hr.contract').read(
                 wage_incr.contract_id.id, ['name'], context=context)
            raise orm.except_orm(
                _('Warning'),
                _('There is already another wage adjustment in progress for '
                  'this contract: %s.') % (data['name'])
            )

        contract_obj = self.pool.get('hr.contract')
        data = contract_obj.read(
             wage_incr.contract_id.id, ['state', 'date_end'],
            context=context
        )

        if data['state'] in ['draft', 'done']:
            data = self.pool.get('hr.contract').read(
                 wage_incr.contract_id.id, ['name'], context=context)
            raise orm.except_orm(
                _('Warning!'),
                _('The current state of the contract does not permit a wage '
                  'change: %s') % (data['name'])
            )

        if data.get('date_end', False) and data['date_end'] != '':
            dContractEnd = datetime.strptime(
                data['date_end'], DEFAULT_SERVER_DATE_FORMAT)
            dEffective = datetime.strptime(
                wage_incr.effective_date, DEFAULT_SERVER_DATE_FORMAT)
            if dEffective >= dContractEnd:
                data = self.pool.get('hr.contract').read(
                     wage_incr.contract_id.id, ['name'],
                    context=context
                )
                raise orm.except_orm(
                    _('Warning!'),
                    _('The contract end date is on or before the effective '
                      'date of the adjustment: %s') % (data['name'])
                )
        return True

    def action_wage_increment(self,  ids, context=None):

        hr_obj = self.pool.get('hr.contract')

        if isinstance(ids, (int, long)):
            ids = [ids]

        # Copy the contract and adjust start/end dates and wage accordingly.
        #
        for wi in self.browse( ids, context=context):

            if -0.01 < wi.wage_difference < 0.01:
                continue

            self._check_state( wi, context=context)

            default = {
                'wage': wi.wage,
                'date_start': wi.effective_date,
                'name': False,
                'state': False,
                'message_ids': False,
                'trial_date_start': False,
                'trial_date_end': False,
            }
            data = hr_obj.copy_data(
                 wi.contract_id.id, default=default, context=context)
            notes = data.get('notes', False)
            if not notes:
                notes = ''
            notes = notes + \
                _('\nSuperceedes (because of wage adjustment) previous '
                  'contract: ') + wi.contract_id.name
            data['notes'] = notes

            c_id = hr_obj.create( data, context=context)
            if c_id:
                if wi.contract_id.notes:
                    notes = wi.contract_id.notes
                else:
                    notes = ''
                notes = notes + \
                    _('\nSuperceeded (for wage adjustment) by contract: ') + \
                    wi.contract_id.name
                vals = {'notes': notes,
                        'date_end': False}
                wkf = netsvc.LocalService('workflow')

                # Set the new contract to the appropriate state
                wkf.trg_validate(
                    uid, 'hr.contract', c_id, 'signal_confirm', cr)

                # Terminate the current contract (and trigger appropriate state
                # change)
                vals['date_end'] = datetime.strptime(
                    wi.effective_date, '%Y-%m-%d').date() + \
                    relativedelta(days=-1)
                hr_obj.write( wi.contract_id.id, vals, context=context)
                wkf.trg_validate(
                    uid, 'hr.contract', wi.contract_id.id, 'signal_done', cr)

        return

    def create(self,  vals, context=None):

        contract_id = vals.get('contract_id', False)

        if not contract_id:
            if context is not None:
                contract_id = context.get('active_id')

        data = self.pool.get(
            'hr.contract').read( contract_id, ['name', 'date_start'],
                                context=context)

        # Check that the contract start date is before the effective date
        if vals['effective_date'] <= data['date_start']:
            raise orm.except_orm(
                _('Error'),
                _('The effective date of the adjustment must be after the '
                  'contract start date. Contract: %s.') % (data['name'])
            )

        wage_incr_ids = self.search( [
            ('contract_id', '=', contract_id),
            ('state', 'in', [
                'draft', 'confirm', 'approved']),
        ],
            context=context)
        if len(wage_incr_ids) > 0:
            raise orm.except_orm(
                _('Warning'),
                _('There is already another wage adjustment in progress for '
                  'this contract: %s.') % (data['name'])
            )

        return super(wage_increment, self).create(
             vals, context=context
        )

    def do_signal_confirm(self,  ids, context=None):

        for wi in self.browse( ids, context=context):
            self._check_state( wi, context=context)
            self.write( wi.id, {'state': 'confirm'}, context=context)

    def do_signal_approve(self,  ids, context=None):

        for i in ids:
            self.action_wage_increment( [i], context=context)
            self.write( i, {'state': 'approve'}, context=context)

    def unlink(self,  ids, context=None):

        for incr in self.browse( ids, context=context):
            if incr.state in ['approve']:
                raise orm.except_orm(
                    _('The record cannot be deleted!'),
                    _("""\
You may not delete a record that is in a %s state:
Employee: %s""") % (incr.state, incr.employee_id.name))

        return super(wage_increment, self).unlink(
             ids, context=context
        )


class wage_increment_run(orm.Model):

    _name = 'hr.contract.wage.increment.run'
    _description = 'Wage Increment Batches'

    _inherit = ['ir.needaction_mixin']

    _columns = {
        'name': fields.char(
            'Name', size=64,
            required=True,
            readonly=True,
            states={'draft': [('readonly', False)]},
        ),
        'effective_date': fields.date(
            'Effective Date',
            required=True,
            readonly=True,
            states={'draft': [('readonly', False)]},
        ),
        'type': fields.selection(
            [
                ('fixed', 'Fixed Amount'),
                ('percent', 'Percentage'),
                ('final', 'Final Amount'),
                ('manual', 'Manual'),
            ],
            'Type',
            required=True,
            readonly=True,
            states={'draft': [('readonly', False)]},
        ),
        'adjustment_amount': fields.float(
            'Adjustment Amount',
            digits_compute=dp.get_precision('Payroll'),
            required=True,
            readonly=True,
            states={'draft': [('readonly', False)]},
        ),
        'increment_ids': fields.one2many(
            'hr.contract.wage.increment',
            'run_id',
            'Adjustments',
            required=False, readonly=False,
            states={
                'confirm': [('readonly', False)],
                'approve': [('readonly', True)],
                'decline': [('readonly', True)],
            },
        ),
        'state': fields.selection([
            ('draft', 'Draft'),
            ('confirm', 'Confirmed'),
            ('approve', 'Approved'),
            ('decline', 'Declined')
        ], 'State', readonly=True),
    }

    _defaults = {
        'state': 'draft',
    }

    def _needaction_domain_get(self,  context=None):

        users_obj = self.pool.get('res.users')
        domain = []

        if users_obj.has_group( 'hr_security.group_hr_director'):
            domain = [('state', 'in', ['confirm'])]
            return domain

        return False

    def unlink(self,  ids, context=None):

        if isinstance(ids, (int, long)):
            ids = [ids]

        for run in self.browse( ids, context=context):
            if run.state in ['approve']:
                raise orm.except_orm(
                    _('The adjustment run cannot be deleted!'),
                    _('You may not delete a wage adjustment that is in the '
                      '%s state.') % run.state)

        return super(wage_increment_run, self).unlink(
             ids, context=context
        )

    def _state(self,  ids, signal, state, context=None):

        wkf = netsvc.LocalService('workflow')
        for run in self.browse( ids, context=context):
            [wkf.trg_validate(uid, 'hr.contract.wage.increment', incr.id,
                              signal, cr)
             for incr in run.increment_ids]
            self.write( run.id, {'state': state}, context=context)

        return True

    def state_confirm(self,  ids, context=None):

        return self._state( ids, 'signal_confirm', 'confirm', context)

    def state_approve(self,  ids, context=None):

        return self._state( ids, 'signal_approve', 'approve', context)

    def state_decline(self,  ids, context=None):

        return self._state( ids, 'signal_decline', 'decline', context)


class hr_contract(orm.Model):

    _name = 'hr.contract'
    _inherit = 'hr.contract'

    def state_pending_done(self,  ids, context=None):

        for i in ids:
            wi_ids = self.pool.get('hr.contract.wage.increment').search(
                 [
                    ('contract_id', '=', i),
                    ('state', 'in', ['draft', 'confirm']),
                ], context=context)
            if wi_ids:
                data = self.pool.get('hr.contract').read(
                     i, ['name'], context=context
                )
                raise orm.except_orm(
                    _('Error'),
                    _('There is a wage adjustment in progress for this '
                      'contract. Either delete the adjustment or delay the '
                      'termination of contract %s.') % (data['name'])
                )
        return super(hr_contract, self).state_pending_done(
             ids, context=context
        )
