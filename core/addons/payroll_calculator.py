# services/payroll_calculator.py
from decimal import Decimal, ROUND_HALF_UP
from datetime import datetime
from ..models import Employee

class PayrollCalculator:
    """Zambian payroll calculator with tax bands and statutory deductions"""
    
    # Zambian Tax Bands 2024
    TAX_BANDS = [
        (0, 4000, Decimal('0.00')),      # 0% up to 4,000
        (4001, 6900, Decimal('0.25')),   # 25% from 4,001 to 6,900
        (6901, 11600, Decimal('0.30')),  # 30% from 6,901 to 11,600
        (11601, None, Decimal('0.375'))  # 37.5% above 11,600
    ]
    
    # NAPSA rates (capped at ZMW 33,248 pensionable earnings)
    NAPSA_RATE = Decimal('0.05')
    NAPSA_MAX_PENSIONABLE = Decimal('33248.00')
    NAPSA_MAX_CONTRIBUTION = NAPSA_MAX_PENSIONABLE * NAPSA_RATE  # ZMW 1,662.40
    
    # NHIMA rates
    NHIMA_RATE = Decimal('0.01')
    
    # Saturnia rates (for permanent employees)
    SATURNIA_RATE = Decimal('0.02')
    
    @classmethod
    def calculate_paye(cls, gross_salary):
        """Calculate PAYE tax based on Zambian progressive tax bands"""
        taxable_income = Decimal(str(gross_salary))
        tax_payable = Decimal('0.00')
        remaining_income = taxable_income
        
        for i, (lower, upper, rate) in enumerate(cls.TAX_BANDS):
            if remaining_income <= 0:
                break
                
            if upper is None:  # Last band (no upper limit)
                band_income = remaining_income
            else:
                band_income = min(remaining_income, Decimal(str(upper)) - Decimal(str(lower)) + Decimal('1'))
                if band_income < 0:
                    band_income = Decimal('0.00')
            
            tax_payable += band_income * rate
            remaining_income -= band_income
        
        return tax_payable.quantize(Decimal('0.01'), rounding=ROUND_HALF_UP)
    
    @classmethod
    def calculate_napsa(cls, basic_salary, is_employee=True):
        """Calculate NAPSA contribution (capped at maximum)"""
        pensionable_earnings = min(Decimal(str(basic_salary)), cls.NAPSA_MAX_PENSIONABLE)
        contribution = pensionable_earnings * cls.NAPSA_RATE
        return contribution.quantize(Decimal('0.01'), rounding=ROUND_HALF_UP)
    
    @classmethod
    def calculate_nhima(cls, basic_salary, is_employee=True):
        """Calculate NHIMA contribution"""
        contribution = Decimal(str(basic_salary)) * cls.NHIMA_RATE
        return contribution.quantize(Decimal('0.01'), rounding=ROUND_HALF_UP)
    
    @classmethod
    def calculate_saturnia(cls, basic_salary, is_employee=True, is_permanent=True):
        """Calculate Saturnia contribution (only for permanent employees)"""
        if not is_permanent:
            return Decimal('0.00')
        contribution = Decimal(str(basic_salary)) * cls.SATURNIA_RATE
        return contribution.quantize(Decimal('0.01'), rounding=ROUND_HALF_UP)
    
    @classmethod
    def calculate_payroll(cls, employee, basic_salary, allowances):
        """Calculate complete payroll for an employee"""
        # Convert to Decimal for precise calculations
        basic = Decimal(str(basic_salary))
        total_allowances = sum(Decimal(str(amount)) for amount in allowances.values())
        gross_pay = basic + total_allowances
        
        # Calculate deductions
        paye = cls.calculate_paye(gross_pay)
        employee_napsa = cls.calculate_napsa(basic_salary, is_employee=True)
        employee_nhima = cls.calculate_nhima(basic_salary, is_employee=True)
        employee_saturnia = cls.calculate_saturnia(basic_salary, is_employee=True, is_permanent=employee.employment_type == 'permanent')
        
        total_deductions = paye + employee_napsa + employee_nhima + employee_saturnia
        net_salary = gross_pay - total_deductions
        
        # Calculate company contributions
        company_napsa = cls.calculate_napsa(basic_salary, is_employee=False)
        company_nhima = cls.calculate_nhima(basic_salary, is_employee=False)
        company_saturnia = cls.calculate_saturnia(basic_salary, is_employee=False, is_permanent=employee.employment_type == 'permanent')
        
        return {
            'basic_salary': float(basic),
            'allowances': allowances,
            'total_allowances': float(total_allowances),
            'gross_pay': float(gross_pay),
            'deductions': {
                'paye': float(paye),
                'employee_napsa': float(employee_napsa),
                'employee_nhima': float(employee_nhima),
                'employee_saturnia': float(employee_saturnia)
            },
            'total_deductions': float(total_deductions),
            'net_salary': float(net_salary),
            'company_contributions': {
                'napsa': float(company_napsa),
                'nhima': float(company_nhima),
                'saturnia': float(company_saturnia)
            }
        }