/* -*- Mode: C; tab-width: 4; indent-tabs-mode: t; c-basic-offset: 4 -*- */
/*
    Gpredict: Real-time satellite tracking and orbit prediction program

    Copyright (C)  2001-2008  Alexandru Csete.

    Comments, questions and bugreports should be submitted via
    http://sourceforge.net/projects/gpredict/
    More details can be found at the project home page:

            http://gpredict.oz9aec.net/
 
    This program is free software; you can redistribute it and/or modify
    it under the terms of the GNU General Public License as published by
    the Free Software Foundation; either version 2 of the License, or
    (at your option) any later version.
  
    This program is distributed in the hope that it will be useful,
    but WITHOUT ANY WARRANTY; without even the implied warranty of
    MERCHANTABILITY or FITNESS FOR A PARTICULAR PURPOSE.  See the
    GNU General Public License for more details.
  
    You should have received a copy of the GNU General Public License
    along with this program; if not, write to the
          Free Software Foundation, Inc.,
      59 Temple Place, Suite 330,
      Boston, MA  02111-1307
      USA
*/
/* Unit test for SGP4 */
#include <stdlib.h>
#include <stdio.h>
#include <string.h>
#include <math.h>
#include "sgp4sdp4.h"

#define TEST_STEPS 5

/* Directory holding the TLE file; set by tests/Makefile.am */
#ifndef TLE_DIR
#define TLE_DIR "."
#endif
#define TLE_FILE TLE_DIR "/test-sgp4.tle"

/* Accuracy check: largest accepted deviation from the Spacetrack Report #3
   values. Those come from a single-precision 1980 implementation, so a
   correct propagator can be some tens of metres off (the code in 2008 was
   off by up to 25 m, the current code by up to 9 m). */
#define STR3_POS_TOL 0.05       /* km */
#define STR3_VEL_TOL 5.0e-5     /* km/s */

/* Regression check: largest accepted deviation from the baseline below,
   loose enough for differences between CPUs and compilers. */
#define REG_POS_TOL 0.001       /* km */
#define REG_VEL_TOL 1.0e-6      /* km/s */

/* structure to hold a set of data */
typedef struct {
    double          t;
    double          x;
    double          y;
    double          z;
    double          vx;
    double          vy;
    double          vz;
} dataset_t;


const dataset_t expected[TEST_STEPS] = {
    {0.0,
     2328.97048951, -5995.22076416, 1719.97067261,
     2.91207230, -0.98341546, -7.09081703},
    {360.0,
     2456.10705566, -6071.93853760, 1222.89727783,
     2.67938992, -0.44829041, -7.22879231},
    {720.0,
     2567.56195068, -6112.50384522, 713.96397400,
     2.44024599, 0.09810869, -7.31995916},
    {1080.0,
     2663.09078980, -6115.48229980, 196.39640427,
     2.19611958, 0.65241995, -7.36282432},
    {1440.0,
     2742.55133057, -6079.67144775, -326.38095856,
     1.94850229, 1.21106251, -7.35619372}
};


/* Output of this code when the regression check was set up (2026-11-01),
   printed with eight decimals. Update it only after checking that a
   change in the results is intended. */
const dataset_t baseline[TEST_STEPS] = {
    {0.0,
     2328.97067989, -5995.22083653, 1719.97067500,
     2.91207227, -0.98341533, -7.09081696},
    {360.0,
     2456.10781852, -6071.93868729, 1222.89565297,
     2.67938912, -0.44828851, -7.22879261},
    {720.0,
     2567.56281750, -6112.50382666, 713.96223091,
     2.44024504, 0.09811071, -7.31995944},
    {1080.0,
     2663.08990111, -6115.48285124, 196.39997366,
     2.19612120, 0.65241594, -7.36282416},
    {1440.0,
     2742.55397964, -6079.67013802, -326.38990978,
     1.94849776, 1.21107244, -7.35619312}
};


/* check digit of a 69 character TLE line, as computed by Checksum_Good() */
static char line_checksum(const char *line)
{
    int             i, sum = 0;

    for (i = 0; i < 68; i++)
    {
        if ((line[i] >= '0') && (line[i] <= '9'))
            sum += line[i] - '0';
        else if (line[i] == '-')
            sum += 1;
    }

    return (char)('0' + sum % 10);
}

char            tle_str[3][80];
sat_t           sat;


/* return 1 if the state in sat deviates from ref by more than the limits */
static int deviates(const sat_t * sat, const dataset_t * ref,
                    double pos_tol, double vel_tol)
{
    return fabs(sat->pos.x - ref->x) > pos_tol ||
        fabs(sat->pos.y - ref->y) > pos_tol ||
        fabs(sat->pos.z - ref->z) > pos_tol ||
        fabs(sat->vel.x - ref->vx) > vel_tol ||
        fabs(sat->vel.y - ref->vy) > vel_tol ||
        fabs(sat->vel.z - ref->vz) > vel_tol;
}

int main(void)
{
    FILE           *fp;
    int             i;
    int             failed = 0;

    /* read tle file */
    fp = fopen(TLE_FILE, "r");
    if (fp != NULL)
    {
        if (fgets(tle_str[0], 80, fp) == NULL)
        {
            printf("Error reading TLE line 1\n");
            fclose(fp);
            return 1;
        }
        if (fgets(tle_str[1], 80, fp) == NULL)
        {
            printf("Error reading TLE line 2\n");
            fclose(fp);
            return 1;
        }
        if (fgets(tle_str[2], 80, fp) == NULL)
        {
            printf("Error reading TLE line 3\n");
            fclose(fp);
            return 1;
        }
        fclose(fp);

        if (Get_Next_Tle_Set(tle_str, &sat.tle) == 1)
        {
            printf("TEST DATA:\n");
        }
        else
        {
            printf("Could not read TLE data 1\n");
            return 1;
        }
    }
    else
    {
        printf("Could not open %s\n", TLE_FILE);
        return 1;
    }

    printf("%s", tle_str[0]);
    printf("%s", tle_str[1]);
    printf("%s", tle_str[2]);

    /* the mean motion field is eleven characters wide */
    if (fabs(sat.tle.xno - 16.05824518) > 1.0e-9)
    {
        printf("Mean motion read as %.8f (expected 16.05824518)\n",
               sat.tle.xno);
        return 1;
    }

    /* a letter in the epoch field must be rejected, even when it
       replaced a 0 and the checksum still holds */
    {
        char            tle_set[139];

        memcpy(tle_set, tle_str[1], 69);
        memcpy(&tle_set[69], tle_str[2], 69);
        tle_set[138] = '\0';

        if (!Good_Elements(tle_set))
        {
            printf("Good_Elements() rejected the unmodified TLE\n");
            return 1;
        }

        tle_set[27] = 'O';      /* epoch 80275.98708465 -> 80275.987O8465 */
        if (Good_Elements(tle_set))
        {
            printf("Good_Elements() accepted a letter in the epoch\n");
            return 1;
        }

        tle_set[27] = '0';
        tle_set[20] = ' ';      /* day of year 5, padded with spaces */
        tle_set[21] = ' ';
        tle_set[68] = line_checksum(tle_set);
        if (!Good_Elements(tle_set))
        {
            printf("Good_Elements() rejected a space-padded day of year\n");
            return 1;
        }
    }

    select_ephemeris(&sat);

    printf("\nDEEP_SPACE_EPHEM: %d (expected 0)\n\n",
           (sat.flags & DEEP_SPACE_EPHEM_FLAG));


    printf("                         RESULT          EXPECTED          "
           "  DELTA\n");
    printf("-----------------------------------------------------------"
           "-------------------\n");

    for (i = 0; i < TEST_STEPS; i++)
    {

        SGP4(&sat, expected[i].t);
        Convert_Sat_State(&sat.pos, &sat.vel);

        printf("STEP %d  t: %6.1f  X: %14.8f   %14.8f   %.8f (%.5f%%)\n",
               i + 1, expected[i].t, sat.pos.x, expected[i].x,
               fabs(sat.pos.x - expected[i].x),
               100.0 * fabs(sat.pos.x - expected[i].x) / fabs(expected[i].x));
        printf("                   Y: %14.8f   %14.8f   %.8f (%.5f%%)\n",
               sat.pos.y, expected[i].y,
               fabs(sat.pos.y - expected[i].y),
               100.0 * fabs(sat.pos.y - expected[i].y) / fabs(expected[i].y));
        printf("                   Z: %14.8f   %14.8f   %.8f (%.5f%%)\n",
               sat.pos.z, expected[i].z,
               fabs(sat.pos.z - expected[i].z),
               100.0 * fabs(sat.pos.z - expected[i].z) / fabs(expected[i].z));
        printf("                  VX: %14.8f   %14.8f   %.8f (%.5f%%)\n",
               sat.vel.x, expected[i].vx,
               fabs(sat.vel.x - expected[i].vx),
               100.0 * fabs(sat.vel.x -
                            expected[i].vx) / fabs(expected[i].vx));
        printf("                  VY: %14.8f   %14.8f   %.8f (%.5f%%)\n",
               sat.vel.y, expected[i].vy, fabs(sat.vel.y - expected[i].vy),
               100.0 * fabs(sat.vel.y -
                            expected[i].vy) / fabs(expected[i].vy));
        printf("                  VZ: %14.8f   %14.8f   %.8f (%.5f%%)\n",
               sat.vel.z, expected[i].vz, fabs(sat.vel.z - expected[i].vz),
               100.0 * fabs(sat.vel.z -
                            expected[i].vz) / fabs(expected[i].vz));

        if (deviates(&sat, &expected[i], STR3_POS_TOL, STR3_VEL_TOL))
        {
            printf("STEP %d  FAILED: deviation from Spacetrack Report #3 "
                   "above %.3f km or %.0e km/s\n",
                   i + 1, STR3_POS_TOL, STR3_VEL_TOL);
            failed = 1;
        }
        if (deviates(&sat, &baseline[i], REG_POS_TOL, REG_VEL_TOL))
        {
            printf("STEP %d  FAILED: deviation from baseline "
                   "above %.3f km or %.0e km/s\n",
                   i + 1, REG_POS_TOL, REG_VEL_TOL);
            failed = 1;
        }
    }

    return failed;
}
